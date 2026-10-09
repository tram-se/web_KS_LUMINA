import hashlib
import hmac
import json
import uuid
from datetime import date
from io import BytesIO
from pathlib import Path

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate
from django.db import transaction
from django.db.models import Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_exempt, ensure_csrf_cookie

import qrcode
import requests
from PIL import Image, ImageDraw, ImageFont
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from admin_panel.models import Room, RoomPrice, RoomType

from .decorators import customer_required
from .forms import (
    BookingRequestForm,
    CustomerLoginForm,
    CustomerProfileForm,
    CustomerRegistrationForm,
    PaymentProofForm,
    RoomSearchForm,
)
from .models import (
    Booking,
    BookingRoom,
    ChatMessage,
    ChatRoom,
    CheckInRequest,
    ConsultationRequest,
    Notification,
    User,
)
from .services import mark_booking_paid


def _public_absolute_url(request, path):
    if settings.PUBLIC_BASE_URL:
        return f"{settings.PUBLIC_BASE_URL}/{path.lstrip('/')}"
    return request.build_absolute_uri(path)


def _branded_qr_png(data, color="#0e716b", label="LUMINA HOTEL", subtitle=""):
    qr = qrcode.QRCode(
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=12,
        border=4,
    )
    qr.add_data(data)
    qr.make(fit=True)
    qr_image = qr.make_image(fill_color=color, back_color="#ffffff").convert("RGB")

    canvas_padding = 36
    label_height = 92 if subtitle else 70
    canvas = Image.new(
        "RGB",
        (
            qr_image.width + canvas_padding * 2,
            qr_image.height + canvas_padding * 2 + label_height,
        ),
        "#ffffff",
    )
    canvas.paste(qr_image, (canvas_padding, canvas_padding))

    draw = ImageDraw.Draw(canvas)
    font_paths = (
        r"C:\Windows\Fonts\segoeuib.ttf",
        r"C:\Windows\Fonts\arialbd.ttf",
    )
    regular_font_paths = (
        r"C:\Windows\Fonts\segoeui.ttf",
        r"C:\Windows\Fonts\arial.ttf",
    )

    def load_font(paths, size):
        for path in paths:
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                continue
        return ImageFont.load_default()

    title_font = load_font(font_paths, 30)
    subtitle_font = load_font(regular_font_paths, 18)
    title_box = draw.textbbox((0, 0), label, font=title_font)
    title_x = (canvas.width - (title_box[2] - title_box[0])) // 2
    title_y = qr_image.height + canvas_padding + 12
    draw.text((title_x, title_y), label, fill=color, font=title_font)

    if subtitle:
        subtitle_box = draw.textbbox((0, 0), subtitle, font=subtitle_font)
        subtitle_x = (canvas.width - (subtitle_box[2] - subtitle_box[0])) // 2
        draw.text(
            (subtitle_x, title_y + 38),
            subtitle,
            fill="#526b68",
            font=subtitle_font,
        )

    return canvas

# Tìm giá phòng đang áp dụng theo ngày nhận phòng
def _room_price(room_type, check_in=None):
    # Tìm mức giá đang hiệu lực tại ngày nhận phòng.
    price_date = check_in or date.today()
    return (
        RoomPrice.objects.filter(
            room_type=room_type,
            is_active=True,
            valid_from__lte=price_date,
        )
        .filter(Q(valid_to__isnull=True) | Q(valid_to__gte=price_date))
        .order_by("-valid_from")
        .first()
    )

# lọc ra các phòng có thể đặt trong khoảng ngày check-in/check-out
def _available_rooms(check_in=None, check_out=None):
    rooms = Room.objects.select_related("room_type").filter(
        room_type__is_active=True,
        room_type__listing_status=RoomType.ListingStatus.PUBLISHED,
        room_type__is_under_maintenance=False,
    )

    if check_in and check_out:
        overlap = (
            Q(bookings__check_in__lt=check_out, bookings__check_out__gt=check_in)
            | Q(
                booking_assignments__booking__check_in__lt=check_out,
                booking_assignments__booking__check_out__gt=check_in,
            )
        ) & ~Q(bookings__status=Booking.Status.CANCELLED) & ~Q(
            booking_assignments__booking__status=Booking.Status.CANCELLED
        )

        rooms = rooms.filter(
            status__in=[
                Room.Status.AVAILABLE,
                Room.Status.DEPOSIT,
                Room.Status.BOOKED,
            ]
        ).exclude(overlap)
    else:
        rooms = rooms.filter(status=Room.Status.AVAILABLE)

    return rooms.distinct()

# đếm số lương phòng trống của hạng phòng trong khoảng ngày check-in/check-out
def _available_quantity(room_type, check_in=None, check_out=None):
    if room_type.is_under_maintenance:
        return 0

    if not check_in or not check_out:
        check_in = date.today()
        check_out = date.today()

    overlap = (
        Q(bookings__check_in__lt=check_out, bookings__check_out__gt=check_in)
        | Q(
            booking_assignments__booking__check_in__lt=check_out,
            booking_assignments__booking__check_out__gt=check_in,
        )
    ) & ~Q(bookings__status=Booking.Status.CANCELLED) & ~Q(
        booking_assignments__booking__status=Booking.Status.CANCELLED
    )

    return (
        Room.objects.filter(
            room_type=room_type,
            status__in=[
                Room.Status.AVAILABLE,
                Room.Status.DEPOSIT,
                Room.Status.BOOKED,
            ],
        )
        .exclude(overlap)
        .distinct()
        .count()
    )

# Xác định trang cần chuyển tới sau đăng nhập/đăng ký và chống redirect không an toàn
def _next_url(request, default="/"):
    target = request.POST.get("next") or request.GET.get("next") or default
    if url_has_allowed_host_and_scheme(
        target,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return target
    return default

#đăng nhập khách hàng, xác thực role và active, lưu session và chuyển hướng
@never_cache
@ensure_csrf_cookie
def customer_login(request):
    form = CustomerLoginForm(request, data=request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.get_user()
        if user and user.role == User.Role.CUSTOMER and user.is_active:
            request.session.cycle_key()
            request.session["customer_user_id"] = user.pk
            messages.success(request, "Đăng nhập khu vực khách hàng thành công.")
            return redirect(_next_url(request))
        form.add_error(None, "Tài khoản này không thuộc khu vực Customer.")
    return render(
        request,
        "accounts/dang_nhap.html",
        {
            "form": form,
            "login_area": "Customer",
            "next_url": _next_url(request),
        },
    )

#đăng ký khách hàng, lưu session và chuyển hướng
@never_cache
@ensure_csrf_cookie
def register(request):
    form = CustomerRegistrationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        request.session.cycle_key()
        request.session["customer_user_id"] = user.pk
        messages.success(request, "Đăng ký tài khoản thành công.")
        return redirect(_next_url(request))
    return render(
        request,
        "accounts/dang_ky.html",
        {"form": form, "next_url": _next_url(request)},
    )

#Phân quyền và điều hướng Admin / Staff / Customer
def dashboard(request):
    if request.user.is_authenticated and request.user.role == User.Role.ADMIN:
        return redirect("admin-home")
    if request.staff_user is not None:
        return redirect("staff-home")
    if request.customer_user is not None:
        return redirect("customer-home")
    return redirect("login")

# Trang chủ khách hàng, hiển thị phòng, giá, số lượng và booking gần đây
def customer_home(request):
    recent_bookings = []
    if request.customer_user is not None:
        recent_bookings = Booking.objects.filter(customer=request.customer_user)[:5]
    room_types = list(
        RoomType.objects.filter(
            is_active=True,
            listing_status=RoomType.ListingStatus.PUBLISHED,
        ).prefetch_related("rooms", "prices", "images", "amenities")
    )
    for room_type in room_types:
        room_type.featured_room = (
            room_type.rooms.filter(status=Room.Status.AVAILABLE).first()
            or room_type.rooms.first()
        )
        room_type.available_quantity = _available_quantity(room_type)
        room_type.current_price = _room_price(room_type)
        uploaded_image = room_type.images.first()
        if uploaded_image:
            room_type.image_url = uploaded_image.image.url
    return render(
        request,
        "accounts/trang_chu_khach_hang.html",
        {
            "recent_bookings": recent_bookings,
            "room_types": room_types,
            "search_form": RoomSearchForm(),
        },
    )

# trang chi tiết booking của khách, hiển thị thông tin phòng, ngày ở, giá và trạng thái thanh toán
@customer_required
def customer_booking_detail(request, booking_id):
    booking = get_object_or_404(
        Booking.objects.select_related("customer", "room"),
        pk=booking_id,
        customer=request.customer_user,
    )
    nights = (booking.check_out - booking.check_in).days
    return render(
        request, "accounts/chi_tiet_dat_phong.html", {"booking": booking, "nights": nights}
    )

# Xử lý thanh toán – gửi biên lai hoặc tạo giao dịch MoMo
@customer_required
def booking_payment(request, booking_id):
    booking = get_object_or_404(
        Booking.objects.select_related("customer", "room"),
        pk=booking_id,
        customer=request.customer_user,
    )
    proof_form = PaymentProofForm(request.POST or None, request.FILES or None)
    if request.method == "POST":
        if proof_form.is_valid():
            booking.payment_reference = proof_form.cleaned_data["payment_reference"].strip()
            booking.payment_proof = proof_form.cleaned_data["payment_proof"]
            booking.payment_status = Booking.PaymentStatus.PENDING
            booking.save(
                update_fields=("payment_reference", "payment_proof", "payment_status", "updated_at")
            )
            messages.success(request, "Đã gửi biên lai. Nhân viên sẽ kiểm tra và xác nhận thanh toán.")
            return redirect("booking-payment", booking_id=booking.pk)
    payment_text = f"LUMINA {booking.booking_code}"
    return render(
        request,
        "accounts/thanh_toan_dat_phong.html",
        {
            "booking": booking,
            "payment_text": payment_text,
        },
    )


@customer_required
def booking_payment_qr(request, booking_id):
    booking = get_object_or_404(
        Booking,
        pk=booking_id,
        customer=request.customer_user,
    )
    scan_url = _public_absolute_url(
        request,
        reverse("payment-qr-scan", kwargs={"token": booking.qr_token}),
    )
    image = _branded_qr_png(
        scan_url,
        color="#0e716b",
        label="VietQR",
        subtitle="QUÉT ĐỂ THANH TOÁN",
    )
    output = BytesIO()
    image.save(output, format="PNG")
    response = HttpResponse(output.getvalue(), content_type="image/png")
    response["Cache-Control"] = "no-store"
    return response


def payment_qr_scan(request, token):
    try:
        token = uuid.UUID(token)
    except (ValueError, TypeError, AttributeError):
        return render(
            request,
            "accounts/ket_qua_quet_thanh_toan.html",
            {"error": "Mã thanh toán không hợp lệ."},
            status=404,
        )
    booking = Booking.objects.filter(qr_token=token).first()
    if booking is None:
        return render(
            request,
            "accounts/ket_qua_quet_thanh_toan.html",
            {"error": "Không tìm thấy booking."},
            status=404,
        )
    if booking.status == Booking.Status.CANCELLED:
        return render(
            request,
            "accounts/ket_qua_quet_thanh_toan.html",
            {"error": "Booking đã bị hủy."},
            status=400,
        )
    mark_booking_paid(booking.pk, f"SIM-{booking.booking_code}")
    return render(
        request,
        "accounts/ket_qua_quet_thanh_toan.html",
        {"booking": Booking.objects.get(pk=booking.pk)},
    )

# trang kết quả thanh toán MoMo, chuyển hướng về chi tiết booking
def booking_payment_result(request, booking_id):
    return redirect("customer-booking-detail", booking_id=booking_id)


@customer_required
def booking_payment_status(request, booking_id):
    booking = get_object_or_404(
        Booking.objects.only("payment_status", "status"),
        pk=booking_id,
        customer=request.customer_user,
    )
    return JsonResponse(
        {
            "payment_status": booking.payment_status,
            "booking_status": booking.status,
            "paid": booking.payment_status == Booking.PaymentStatus.PAID,
        }
    )


@csrf_exempt
def bank_payment_webhook(request):
    if request.method != "POST":
        return HttpResponse(status=405)
    configured_token = settings.PAYMENT_WEBHOOK_TOKEN
    authorization = request.headers.get("Authorization", "")
    supplied_token = request.headers.get("X-Webhook-Token", "")
    if authorization.lower().startswith("bearer "):
        supplied_token = authorization[7:].strip()
    if not configured_token:
        return JsonResponse({"ok": False, "error": "Webhook is not configured"}, status=503)
    if not hmac.compare_digest(configured_token, supplied_token):
        return HttpResponse(status=403)
    try:
        payload = json.loads(request.body)
        amount = int(payload.get("transferAmount", payload.get("amount", 0)))
    except (TypeError, ValueError, json.JSONDecodeError):
        return JsonResponse({"ok": False, "error": "Invalid payload"}, status=400)

    content = " ".join(
        str(payload.get(key, ""))
        for key in ("content", "description", "transferDescription", "orderInfo")
    ).upper()
    booking = Booking.objects.filter(booking_code__iexact=content).first()
    if booking is None:
        booking_code = next(
            (code for code in content.split() if code.startswith("BK-")), None
        )
        booking = Booking.objects.filter(booking_code__iexact=booking_code).first()
    if booking is None or booking.status == Booking.Status.CANCELLED:
        return JsonResponse({"ok": False, "error": "Booking is unavailable"}, status=400)
    if amount != int(booking.total_price):
        return JsonResponse({"ok": False, "error": "Booking or amount mismatch"}, status=400)

    reference = str(
        payload.get("id")
        or payload.get("referenceCode")
        or payload.get("transactionId")
        or ""
    )
    marked_booking, changed = mark_booking_paid(booking.pk, reference)
    return JsonResponse(
        {"ok": True, "booking": marked_booking.booking_code, "changed": changed}
    )

# Nhận kết quả thanh toán từ MoMo, kiểm tra chữ ký và cập nhật trạng thái đã thanh toán
@csrf_exempt
def momo_ipn(request):
    if request.method != "POST":
        return HttpResponse(status=405)
    try:
        payload = json.loads(request.body)
    except (TypeError, ValueError):
        return HttpResponse(status=400)
    if payload.get("partnerCode") != settings.MOMO_PARTNER_CODE:
        return HttpResponse(status=400)
    raw_signature = (
        f"accessKey={settings.MOMO_ACCESS_KEY}&amount={payload.get('amount', '')}"
        f"&extraData={payload.get('extraData', '')}&message={payload.get('message', '')}"
        f"&orderId={payload.get('orderId', '')}&orderInfo={payload.get('orderInfo', '')}"
        f"&orderType={payload.get('orderType', '')}&partnerCode={payload.get('partnerCode', '')}"
        f"&payType={payload.get('payType', '')}&requestId={payload.get('requestId', '')}"
        f"&responseTime={payload.get('responseTime', '')}&resultCode={payload.get('resultCode', '')}"
        f"&transId={payload.get('transId', '')}"
    )
    expected = hmac.new(settings.MOMO_SECRET_KEY.encode(), raw_signature.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, payload.get("signature", "")):
        return HttpResponse(status=403)
    booking = Booking.objects.filter(momo_order_id=payload.get("orderId")).first()
    if booking is None:
        return HttpResponse(status=404)
    if payload.get("resultCode") == 0:
        mark_booking_paid(booking.pk, str(payload.get("transId", "")))
    return HttpResponse(json.dumps({"resultCode": 0}), content_type="application/json")

#Tạo và trả về hóa đơn/PDF xác nhận đặt phòng
def booking_invoice(request, booking_id):
    queryset = Booking.objects.select_related("customer", "room")
    booking = get_object_or_404(queryset, pk=booking_id)
    if not (
        request.customer_user is not None and booking.customer_id == request.customer_user.pk
    ) and request.staff_user is None:
        return redirect("login")
    return _booking_confirmation_pdf(booking)

# Tạo mã QR cho booking để khách sử dụng
@customer_required
def booking_qr(request, booking_id):
    # Sinh ảnh QR chứa URL tra cứu booking cho khách đã được xác nhận.
    booking = get_object_or_404(
        Booking.objects.select_related("customer", "room"),
        pk=booking_id,
        customer=request.customer_user,
        status__in=(Booking.Status.CONFIRMED, Booking.Status.CHECKED_IN),
    )
    scan_url = _public_absolute_url(
        request,
        reverse("booking-qr-scan", kwargs={"token": booking.qr_token}),
    )
    image = _branded_qr_png(scan_url, color="#147a72")
    output = BytesIO()
    image.save(output, format="PNG")
    response = HttpResponse(output.getvalue(), content_type="image/png")
    response["Cache-Control"] = "no-store"
    if request.GET.get("download") == "1":
        response["Content-Disposition"] = (
            f'attachment; filename="{booking.booking_code}.png"'
        )
    return response

# Khi quét QR: kiểm tra booking → trạng thái → tạo yêu cầu check-in
def booking_qr_scan(request, token):
    # Giải mã token, kiểm tra trạng thái booking và tạo yêu cầu check-in nếu cần.
    try:
        token = uuid.UUID(token)
    except (ValueError, TypeError, AttributeError):
        return render(
            request,
            "accounts/ket_qua_quet_qr.html",
            {"error": "QR Booking không tồn tại hoặc không hợp lệ."},
            status=404,
        )
    booking = Booking.objects.select_related("customer", "room").filter(
        qr_token=token
    ).first()
    if booking is None:
        return render(
            request,
            "accounts/ket_qua_quet_qr.html",
            {"error": "QR Booking không tồn tại hoặc không hợp lệ."},
            status=404,
        )
    if booking.status == Booking.Status.CANCELLED:
        return render(request, "accounts/ket_qua_quet_qr.html", {"error": "Booking này đã bị hủy."})
    if booking.status == Booking.Status.PENDING:
        return render(request, "accounts/ket_qua_quet_qr.html", {"error": "Booking chưa được xác nhận."})
    if booking.status == Booking.Status.CHECKED_OUT:
        return render(request, "accounts/ket_qua_quet_qr.html", {"error": "Booking đã check-out."})
    with transaction.atomic():
        locked_booking = Booking.objects.select_for_update().get(pk=booking.pk)
        request_record = getattr(locked_booking, "check_in_request", None)
        if locked_booking.status == Booking.Status.CHECKED_IN:
            pass
        elif request_record is None:
            request_record, created = CheckInRequest.objects.get_or_create(
                booking=locked_booking,
                defaults={"status": CheckInRequest.Status.PENDING},
            )
        elif request_record.status == CheckInRequest.Status.REJECTED:
            pass
    return _booking_confirmation_pdf(booking)

# Tạo file PDF xác nhận đặt phòng
def _booking_confirmation_pdf(booking):
    """Create the confirmation document opened when a booking QR is scanned."""
    # Tạo phiếu PDF xác nhận gồm khách, phòng, ngày ở và thanh toán.
    output = BytesIO()
    font_path = Path("C:/Windows/Fonts/arial.ttf")
    bold_font_path = Path("C:/Windows/Fonts/arialbd.ttf")
    font_name = "Helvetica"
    bold_font_name = "Helvetica-Bold"
    if font_path.exists() and bold_font_path.exists():
        pdfmetrics.registerFont(TTFont("LuminaArial", str(font_path)))
        pdfmetrics.registerFont(TTFont("LuminaArialBold", str(bold_font_path)))
        font_name = "LuminaArial"
        bold_font_name = "LuminaArialBold"

    document = SimpleDocTemplate(
        output,
        pagesize=A4,
        rightMargin=42,
        leftMargin=42,
        topMargin=42,
        bottomMargin=42,
        title=f"Xac nhan dat phong {booking.booking_code}",
    )
    styles = getSampleStyleSheet()
    title_style = styles["Title"]
    title_style.fontName = bold_font_name
    body_style = styles["BodyText"]
    body_style.fontName = font_name
    body_style.leading = 18
    story = [
        Paragraph("PHIEU XAC NHAN DAT PHONG", title_style),
        Spacer(1, 14),
        Paragraph(f"Ma booking: {booking.booking_code}", body_style),
        Spacer(1, 10),
    ]
    rows = [
        ["Ho va ten", booking.guest_full_name or booking.customer.full_name],
        ["So dien thoai", booking.guest_phone or booking.customer.phone_number or "Chua cap nhat"],
        ["So CCCD", booking.guest_id_number or "Chua cap nhat"],
        ["Loai phong", booking.room_type],
        [
            "So phong",
            ", ".join(booking.room_assignments.values_list("room__number", flat=True))
            or (booking.room.number if booking.room else "Chua gan"),
        ],
        ["So luong phong", str(booking.room_quantity)],
        ["So khach", f"{booking.guest_count} nguoi"],
        ["Check-in", f"{booking.check_in:%d/%m/%Y} - {booking.check_in_time:%H:%M}"],
        ["Check-out", f"{booking.check_out:%d/%m/%Y} - {booking.check_out_time:%H:%M}"],
        ["Tong tien", f"{booking.total_price:,.0f} VND"],
        ["Thanh toan", booking.get_payment_status_display()],
        ["Ma giao dich", booking.payment_reference or "Chua co"],
        ["Trang thai", booking.get_status_display()],
    ]
    table = Table(rows, colWidths=[125, 350])
    table.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, -1), font_name),
                ("FONTNAME", (0, 0), (0, -1), bold_font_name),
                ("FONTSIZE", (0, 0), (-1, -1), 11),
                ("LEADING", (0, 0), (-1, -1), 16),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#d9e3df")),
                ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#edf5f1")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 9),
                ("RIGHTPADDING", (0, 0), (-1, -1), 9),
            ]
        )
    )
    story.append(table)
    document.build(story)
    response = HttpResponse(output.getvalue(), content_type="application/pdf")
    response["Content-Disposition"] = (
        f'inline; filename="{booking.booking_code}-confirmation.pdf"'
    )
    return response

# Tìm kiếm, lọc phòng theo ngày, số khách, loại phòng và giá
def room_list(request):
    # Tìm kiếm phòng theo ngày nhận/trả, số khách, hạng phòng và ngân sách.
    form = RoomSearchForm(request.GET or None)
    rooms = Room.objects.none()
    if form.is_valid():
        cleaned_data = form.cleaned_data
        rooms = _available_rooms(
            cleaned_data.get("check_in"),
            cleaned_data.get("check_out"),
        )
        requested_quantity = cleaned_data.get("room_quantity") or 1
        room_type = cleaned_data.get("room_type")
        guests = cleaned_data.get("guests")
        max_price = cleaned_data.get("max_price")
        check_in = cleaned_data.get("check_in")
        check_out = cleaned_data.get("check_out")
        # Tách danh sách phòng có thể đặt theo đúng khoảng ngày khách chọn.
        available_rooms = _available_rooms(check_in, check_out)
        all_rooms = Room.objects.select_related("room_type").filter(
            room_type__is_active=True,
            room_type__listing_status=RoomType.ListingStatus.PUBLISHED,
        )
        rooms = all_rooms
        if room_type:
            rooms = rooms.filter(room_type=room_type)
        if guests:
            # Sức chứa được tính theo tổng số phòng khách yêu cầu.
            minimum_room_capacity = (guests + requested_quantity - 1) // requested_quantity
            rooms = rooms.filter(room_type__max_guests__gte=minimum_room_capacity)
        room_list = []
        seen_types = set()
        for room in rooms:
            room.available_quantity = _available_quantity(room.room_type, check_in, check_out)
            if room.room_type_id in seen_types:
                continue
            seen_types.add(room.room_type_id)
            room.is_available = room.available_quantity >= requested_quantity
            room.requested_quantity = requested_quantity
            room.selected_check_in = check_in
            room.selected_check_out = check_out
            uploaded_image = room.room_type.images.first()
            if uploaded_image:
                room.room_type.image_url = uploaded_image.image.url
            price = _room_price(room.room_type, cleaned_data.get("check_in"))
            room.current_price = price.price if price else None
            room_list.append(room)
        if max_price is not None:
            room_list = [
                room
                for room in room_list
                if room.current_price is not None and room.current_price <= max_price
            ]
        rooms = room_list
    return render(request, "accounts/danh_sach_phong.html", {"form": form, "rooms": rooms})

#Hiển thị chi tiết phòng + xử lý đặt phòng
def room_detail(request, room_id):
    # Hiển thị chi tiết phòng và xử lý yêu cầu đặt phòng của khách.
    room = get_object_or_404(
        Room.objects.select_related("room_type"),
        pk=room_id,
        room_type__is_active=True,
        room_type__listing_status=RoomType.ListingStatus.PUBLISHED,
    )
    form = BookingRequestForm(
        request.POST or None,
        request.FILES or None,
        customer=request.customer_user,
    )
    requested_quantity = 1
    if request.method != "POST":
        try:
            requested_quantity = max(1, int(request.GET.get("room_quantity", 1)))
        except (TypeError, ValueError):
            requested_quantity = 1
        form.fields["room_quantity"].initial = requested_quantity
    uploaded_image = room.room_type.images.first()
    if uploaded_image:
        room.room_type.image_url = uploaded_image.image.url
    selected_check_in = selected_check_out = None
    if request.method == "POST":
        selected_check_in = selected_check_out = None
    else:
        try:
            selected_check_in = date.fromisoformat(request.GET.get("check_in", ""))
            selected_check_out = date.fromisoformat(request.GET.get("check_out", ""))
        except (TypeError, ValueError):
            selected_check_in = selected_check_out = None
    room.available_quantity = _available_quantity(
        room.room_type,
        selected_check_in,
        selected_check_out,
    )
    room.is_available = (
        _available_quantity(room.room_type, selected_check_in, selected_check_out)
        >= requested_quantity
    )
    room.selected_check_in = selected_check_in
    room.selected_check_out = selected_check_out
    price = _room_price(room.room_type, selected_check_in)
    if request.method == "POST" and request.customer_user is None:
        login_url = reverse("login")
        return redirect(f"{login_url}?next={request.path}")
    if request.method == "POST" and room.room_type.is_under_maintenance:
        form.add_error(None, "Hạng phòng đang được sửa chữa và tạm ngưng nhận đặt.")
    elif request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        available_quantity = _available_quantity(
            room.room_type,
            data["check_in"],
            data["check_out"],
        )
        room.available_quantity = available_quantity
        room.is_available = available_quantity >= data["room_quantity"]
        if available_quantity < data["room_quantity"]:
            form.add_error(None, f"Chỉ còn {available_quantity} phòng trong khoảng thời gian bạn chọn.")
        elif data["guest_count"] > room.room_type.max_guests * data["room_quantity"]:
            total_capacity = room.room_type.max_guests * data["room_quantity"]
            form.add_error(
                "guest_count",
                f"Số khách vượt quá sức chứa của {data['room_quantity']} phòng "
                f"(tối đa {total_capacity} khách).",
            )
        elif price is None:
            form.add_error(None, "Phòng chưa có giá áp dụng cho thời gian này.")
        else:
            with transaction.atomic():
                available_rooms = list(
                    _available_rooms(data["check_in"], data["check_out"])
                    .select_for_update()
                    .filter(room_type=room.room_type)[: data["room_quantity"]]
                )
                if len(available_rooms) < data["room_quantity"]:
                    form.add_error(
                        None, "Phòng không còn trống trong khoảng thời gian này."
                    )
                    return render(
                        request,
                        "accounts/chi_tiet_phong.html",
                        {"room": room, "price": price, "form": form},
                    )
                nights = (data["check_out"] - data["check_in"]).days
                total_price = price.price * nights * data["room_quantity"]
                booking = Booking.objects.create(
                    customer=request.customer_user,
                    guest_full_name=data["guest_full_name"],
                    guest_phone=data["guest_phone"],
                    guest_id_number=data["guest_id_number"],
                    id_card_front_image=data["id_card_front_image"],
                    id_card_back_image=data["id_card_back_image"],
                    room=available_rooms[0],
                    booking_code=f"BK-{data['check_in']:%Y%m%d}-{uuid.uuid4().hex[:4].upper()}",
                    room_type=room.room_type.name,
                    check_in=data["check_in"],
                    check_in_time=data["check_in_time"],
                    check_out=data["check_out"],
                    check_out_time=data["check_out_time"],
                    guest_count=data["guest_count"],
                    room_quantity=data["room_quantity"],
                    total_price=total_price,
                    notes=data["notes"],
                )
                BookingRoom.objects.bulk_create(
                    [
                        BookingRoom(booking=booking, room=assigned_room)
                        for assigned_room in available_rooms
                    ]
                )
                Room.objects.filter(
                    pk__in=[assigned_room.pk for assigned_room in available_rooms]
                ).update(status=Room.Status.DEPOSIT)
                # Báo cho toàn bộ nhân viên active biết có booking cần duyệt.
                staff_users = User.objects.filter(role=User.Role.STAFF, is_active=True)
                Notification.objects.bulk_create(
                    [
                        Notification(
                            recipient=staff_user,
                            booking=booking,
                            title="Có yêu cầu đặt phòng mới",
                            message=f"{booking.booking_code} đang chờ duyệt cho hạng {booking.room_type}.",
                        )
                        for staff_user in staff_users
                    ]
                )
            messages.success(
                request,
                f"Đã tạo booking {booking.booking_code}. Vui lòng thanh toán để xác nhận phòng.",
            )
            return redirect("customer-booking-detail", booking_id=booking.pk)
    return render(
        request,
        "accounts/chi_tiet_phong.html",
        {"room": room, "price": price, "form": form},
    )

# Hiển thị thông báo của khách hàng và đánh dấu đã đọc
def customer_notifications(request):
    # Hiển thị và đánh dấu đã đọc các thông báo của khách hàng.
    if request.customer_user is None:
        return redirect("login")
    notifications = Notification.objects.filter(recipient=request.customer_user)
    notifications.filter(is_read=False).update(is_read=True)
    return render(request, "accounts/thong_bao.html", {"notifications": notifications})

# Xem/chỉnh sửa thông tin tài khoản khách hàng
@customer_required
def customer_profile(request):
    form = CustomerProfileForm(request.POST or None, instance=request.customer_user)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Đã cập nhật thông tin tài khoản.")
        return redirect("customer-profile")
    return render(request, "accounts/ho_so_khach_hang.html", {"form": form})

#đăng xuất khách hàng, xóa session và chuyển hướng về trang đăng nhập
def customer_logout(request):
    if request.method == "POST":
        request.session.pop("customer_user_id", None)
        return redirect("customer-home")
    return render(
        request,
        "accounts/dang_xuat.html",
        {"logout_area": "Customer", "cancel_url": "/customer/"},
    )
# Trang tư vấn khách hàng
@customer_required
def customer_consultation(request):
    return render(
        request,
        "accounts/tu_van_khach_hang.html"
    )