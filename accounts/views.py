import hashlib
import hmac
import json
import uuid
from datetime import date
from io import BytesIO
from pathlib import Path

from django.contrib import messages
from django.contrib.auth import authenticate
from django.db import transaction
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.conf import settings
from django.core.files.storage import default_storage
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.csrf import csrf_exempt
from django.shortcuts import redirect, render
import qrcode
import requests
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from reportlab.lib import colors

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
from .models import Booking, CheckInRequest, User


def _room_price(room_type, check_in=None):
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


def _available_rooms(check_in=None, check_out=None):
    rooms = Room.objects.select_related("room_type").filter(
        room_type__is_active=True,
        room_type__listing_status=RoomType.ListingStatus.PUBLISHED,
    )
    if check_in and check_out:
        rooms = rooms.filter(status=Room.Status.AVAILABLE).exclude(
            bookings__status=Booking.Status.CANCELLED,
            bookings__check_in__lt=check_out,
            bookings__check_out__gt=check_in,
        )
    else:
        rooms = rooms.filter(status=Room.Status.AVAILABLE)
    return rooms.distinct()


def _available_quantity(room_type, check_in=None, check_out=None):
    """Count rooms without a non-cancelled booking overlapping the requested stay."""
    if not check_in or not check_out:
        check_in = date.today()
        check_out = date.today()

    overlap = Q(
        bookings__check_in__lt=check_out,
        bookings__check_out__gt=check_in,
    ) & ~Q(bookings__status=Booking.Status.CANCELLED)
    return (
        Room.objects.filter(room_type=room_type, status=Room.Status.AVAILABLE)
        .exclude(overlap)
        .distinct()
        .count()
    )


def _next_url(request, default="/customer/"):
    target = request.POST.get("next") or request.GET.get("next") or default
    if url_has_allowed_host_and_scheme(
        target,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return target
    return default


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
        "accounts/login.html",
        {
            "form": form,
            "login_area": "Customer",
            "next_url": _next_url(request),
        },
    )


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
        "accounts/register.html",
        {"form": form, "next_url": _next_url(request)},
    )


def dashboard(request):
    if request.user.is_authenticated and request.user.role == User.Role.ADMIN:
        return redirect("admin-home")
    if request.staff_user is not None:
        return redirect("staff-home")
    if request.customer_user is not None:
        return redirect("customer-home")
    return redirect("login")


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
        "accounts/customer_home.html",
        {"recent_bookings": recent_bookings, "room_types": room_types},
    )


@customer_required
def customer_booking_detail(request, booking_id):
    booking = get_object_or_404(
        Booking.objects.select_related("customer", "room"),
        pk=booking_id,
        customer=request.customer_user,
    )
    nights = (booking.check_out - booking.check_in).days
    return render(
        request, "accounts/booking_detail.html", {"booking": booking, "nights": nights}
    )


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
            return redirect("customer-booking-detail", booking_id=booking.pk)
        if not all((settings.MOMO_PARTNER_CODE, settings.MOMO_ACCESS_KEY, settings.MOMO_SECRET_KEY)):
            pass
        else:
            messages.info(request, "Để thanh toán tự động, hãy dùng MoMo Merchant API.")
        order_id = f"{booking.booking_code}-{uuid.uuid4().hex[:8].upper()}"
        request_id = uuid.uuid4().hex
        return_url = settings.MOMO_RETURN_URL or request.build_absolute_uri(
            reverse("booking-payment-result", kwargs={"booking_id": booking.pk})
        )
        ipn_url = settings.MOMO_IPN_URL or request.build_absolute_uri(reverse("momo-ipn"))
        order_info = f"Thanh toan {booking.booking_code}"
        raw_signature = (
            f"accessKey={settings.MOMO_ACCESS_KEY}&amount={int(booking.total_price)}"
            f"&extraData={booking.pk}&ipnUrl={ipn_url}&orderId={order_id}"
            f"&orderInfo={order_info}&partnerCode={settings.MOMO_PARTNER_CODE}"
            f"&redirectUrl={return_url}&requestId={request_id}&requestType=captureWallet"
        )
        signature = hmac.new(settings.MOMO_SECRET_KEY.encode(), raw_signature.encode(), hashlib.sha256).hexdigest()
        payload = {
            "partnerCode": settings.MOMO_PARTNER_CODE,
            "requestId": request_id,
            "amount": int(booking.total_price),
            "orderId": order_id,
            "orderInfo": order_info,
            "redirectUrl": return_url,
            "ipnUrl": ipn_url,
            "lang": "vi",
            "extraData": str(booking.pk),
            "requestType": "captureWallet",
            "signature": signature,
        }
        try:
            momo_response = requests.post(settings.MOMO_API_URL, json=payload, timeout=30).json()
        except (requests.RequestException, ValueError):
            messages.error(request, "Không thể kết nối MoMo. Vui lòng thử lại.")
            return redirect("booking-payment", booking_id=booking.pk)
        if momo_response.get("resultCode") != 0 or not momo_response.get("payUrl"):
            messages.error(request, momo_response.get("message", "MoMo từ chối tạo giao dịch."))
            return redirect("booking-payment", booking_id=booking.pk)
        booking.momo_order_id = order_id
        booking.momo_request_id = request_id
        booking.payment_status = Booking.PaymentStatus.PENDING
        booking.save(update_fields=("momo_order_id", "momo_request_id", "payment_status", "updated_at"))
        return redirect(momo_response["payUrl"])
    payment_text = f"LUMINA {booking.booking_code}"
    qr_data = (
        f"https://img.vietqr.io/image/{settings.PAYMENT_BANK_ID}-"
        f"{settings.PAYMENT_BANK_ACCOUNT}-compact2.png?amount={int(booking.total_price)}"
        f"&addInfo={payment_text.replace(' ', '%20')}&accountName={settings.PAYMENT_BANK_ACCOUNT_NAME.replace(' ', '%20')}"
    )
    momo_qr_url = None
    if default_storage.exists(settings.MOMO_QR_IMAGE):
        momo_qr_url = default_storage.url(settings.MOMO_QR_IMAGE)
    return render(
        request,
        "accounts/booking_payment.html",
        {
            "booking": booking,
            "payment_text": payment_text,
            "qr_data": qr_data,
            "momo_qr_url": momo_qr_url,
            "proof_form": proof_form,
        },
    )


def booking_payment_result(request, booking_id):
    return redirect("customer-booking-detail", booking_id=booking_id)


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
        booking.payment_status = Booking.PaymentStatus.PAID
        booking.payment_reference = str(payload.get("transId", ""))
        booking.paid_at = timezone.now()
        booking.save(update_fields=("payment_status", "payment_reference", "paid_at", "updated_at"))
    return HttpResponse(json.dumps({"resultCode": 0}), content_type="application/json")
def booking_invoice(request, booking_id):
    queryset = Booking.objects.select_related("customer", "room")
    booking = get_object_or_404(queryset, pk=booking_id)
    if not (
        request.customer_user is not None and booking.customer_id == request.customer_user.pk
    ) and request.staff_user is None:
        return redirect("login")
    return _booking_confirmation_pdf(booking)


@customer_required
def booking_qr(request, booking_id):
    booking = get_object_or_404(
        Booking.objects.select_related("customer", "room"),
        pk=booking_id,
        customer=request.customer_user,
        status__in=(Booking.Status.CONFIRMED, Booking.Status.CHECKED_IN),
    )
    scan_url = request.build_absolute_uri(
        reverse("booking-qr-scan", kwargs={"token": booking.qr_token})
    )
    image = qrcode.make(scan_url)
    output = BytesIO()
    image.save(output, format="PNG")
    response = HttpResponse(output.getvalue(), content_type="image/png")
    if request.GET.get("download") == "1":
        response["Content-Disposition"] = (
            f'attachment; filename="{booking.booking_code}.png"'
        )
    return response


def booking_qr_scan(request, token):
    try:
        token = uuid.UUID(token)
    except (ValueError, TypeError, AttributeError):
        return render(
            request,
            "accounts/qr_scan_result.html",
            {"error": "QR Booking không tồn tại hoặc không hợp lệ."},
            status=404,
        )
    booking = Booking.objects.select_related("customer", "room").filter(
        qr_token=token
    ).first()
    if booking is None:
        return render(
            request,
            "accounts/qr_scan_result.html",
            {"error": "QR Booking không tồn tại hoặc không hợp lệ."},
            status=404,
        )
    if booking.status == Booking.Status.CANCELLED:
        return render(request, "accounts/qr_scan_result.html", {"error": "Booking này đã bị hủy."})
    if booking.status == Booking.Status.PENDING:
        return render(request, "accounts/qr_scan_result.html", {"error": "Booking chưa được xác nhận."})
    if booking.status == Booking.Status.CHECKED_OUT:
        return render(request, "accounts/qr_scan_result.html", {"error": "Booking đã check-out."})
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


def _booking_confirmation_pdf(booking):
    """Create the confirmation document opened when a booking QR is scanned."""
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
        ["So phong", booking.room.number if booking.room else "Chua gan"],
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


def room_list(request):
    form = RoomSearchForm(request.GET or None)
    rooms = Room.objects.none()
    if form.is_valid() or not request.GET:
        cleaned_data = form.cleaned_data if form.is_valid() else {}
        rooms = _available_rooms(
            cleaned_data.get("check_in"),
            cleaned_data.get("check_out"),
        )
        room_type = cleaned_data.get("room_type")
        guests = cleaned_data.get("guests")
        max_price = cleaned_data.get("max_price")
        check_in = cleaned_data.get("check_in")
        check_out = cleaned_data.get("check_out")
        available_rooms = _available_rooms(check_in, check_out)
        all_rooms = Room.objects.select_related("room_type").filter(
            room_type__is_active=True,
            room_type__listing_status=RoomType.ListingStatus.PUBLISHED,
        )
        rooms = all_rooms
        if room_type:
            rooms = rooms.filter(room_type=room_type)
        if guests:
            rooms = rooms.filter(room_type__max_guests__gte=guests)
        room_list = []
        seen_types = set()
        for room in rooms:
            if room.room_type_id in seen_types:
                continue
            seen_types.add(room.room_type_id)
            room.available_quantity = _available_quantity(
                room.room_type,
                check_in,
                check_out,
            )
            room.selected_check_in = check_in
            room.selected_check_out = check_out
            available_room = available_rooms.filter(
                room_type_id=room.room_type_id
            ).first()
            if available_room:
                room = available_room
                room.available_quantity = _available_quantity(
                    room.room_type, check_in, check_out
                )
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
    return render(request, "accounts/room_list.html", {"form": form, "rooms": rooms})


def room_detail(request, room_id):
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
    room.is_available = room.available_quantity > 0
    room.selected_check_in = selected_check_in
    room.selected_check_out = selected_check_out
    price = _room_price(room.room_type)
    if request.method == "POST" and request.customer_user is None:
        login_url = reverse("login")
        return redirect(f"{login_url}?next={request.path}")
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        available_rooms = _available_quantity(
            room.room_type,
            data["check_in"],
            data["check_out"],
        )
        room.available_quantity = available_rooms
        room.is_available = available_rooms > 0
        if available_rooms <= 0:
            form.add_error(None, "Phòng đã hết trong khoảng thời gian bạn chọn.")
        elif data["guest_count"] > room.room_type.max_guests:
            form.add_error("guest_count", "Số khách vượt quá sức chứa của phòng.")
        elif price is None:
            form.add_error(None, "Phòng chưa có giá áp dụng cho thời gian này.")
        else:
            with transaction.atomic():
                available_room = (
                    _available_rooms(data["check_in"], data["check_out"])
                    .select_for_update()
                    .filter(room_type=room.room_type)
                    .first()
                )
                if available_room is None:
                    form.add_error(
                        None, "Phòng không còn trống trong khoảng thời gian này."
                    )
                    return render(
                        request,
                        "accounts/room_detail.html",
                        {"room": room, "price": price, "form": form},
                    )
                nights = (data["check_out"] - data["check_in"]).days
                total_price = price.price * nights
                booking = Booking.objects.create(
                    customer=request.customer_user,
                    guest_full_name=data["guest_full_name"],
                    guest_phone=data["guest_phone"],
                    guest_id_number=data["guest_id_number"],
                    id_card_front_image=data["id_card_front_image"],
                    id_card_back_image=data["id_card_back_image"],
                    room=available_room,
                    booking_code=f"BK-{data['check_in']:%Y%m%d}-{uuid.uuid4().hex[:4].upper()}",
                    room_type=room.room_type.name,
                    check_in=data["check_in"],
                    check_in_time=data["check_in_time"],
                    check_out=data["check_out"],
                    check_out_time=data["check_out_time"],
                    guest_count=data["guest_count"],
                    total_price=total_price,
                    notes=data["notes"],
                )
            messages.success(
                request,
                f"Đã gửi yêu cầu đặt phòng {booking.booking_code}.",
            )
            return redirect("customer-booking-detail", booking_id=booking.pk)
    return render(
        request,
        "accounts/room_detail.html",
        {"room": room, "price": price, "form": form},
    )


@customer_required
def customer_profile(request):
    form = CustomerProfileForm(request.POST or None, instance=request.customer_user)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Đã cập nhật thông tin tài khoản.")
        return redirect("customer-profile")
    return render(request, "accounts/customer_profile.html", {"form": form})


def customer_logout(request):
    if request.method == "POST":
        request.session.pop("customer_user_id", None)
        return redirect("login")
    return render(
        request,
        "accounts/logout.html",
        {"logout_area": "Customer", "cancel_url": "/customer/"},
    )
