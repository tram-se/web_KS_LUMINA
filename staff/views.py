from datetime import date, timedelta
import json

# pyrefly: ignore [missing-import]
from django.contrib import messages
# pyrefly: ignore [missing-import]
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from accounts.decorators import staff_required
from accounts.chatbot import generate_bot_response, parse_intent
from accounts.models import (
    Booking,
    ChatMessage,
    ChatRoom,
    CheckInRequest,
    ConsultationRequest,
    Notification,
    User,
)
from admin_panel.models import Room, RoomImage, RoomPrice, RoomType

from .forms import (
    BookingStatusForm,
    ConsultationStatusForm,
    CustomerUpdateForm,
    RoomListingEditForm,
    RoomListingForm,
)
from accounts.services import mark_booking_paid


# Trang tổng quan Staff – thống kê booking, check-in, tư vấn, khách hàng và booking gần đây
@staff_required
def staff_home(request):
    context = {
        "pending_bookings": Booking.objects.filter(
            status=Booking.Status.PENDING
        ).count(),
        "confirmed_bookings": Booking.objects.filter(
            status=Booking.Status.CONFIRMED
        ).count(),
        "pending_checkin_requests": CheckInRequest.objects.filter(
            status=CheckInRequest.Status.PENDING,
            booking__status=Booking.Status.CONFIRMED,
        ).count(),
        "pending_checkin_requests_list": CheckInRequest.objects.filter(
            status=CheckInRequest.Status.PENDING,
            booking__status=Booking.Status.CONFIRMED,
        ).select_related("booking", "booking__customer", "booking__room")[:10],
        "new_consultations": ConsultationRequest.objects.filter(
            status=ConsultationRequest.Status.NEW
        ).count(),
        "customer_count": User.objects.filter(role=User.Role.CUSTOMER).count(),
        "recent_bookings": Booking.objects.select_related("customer")[:5],
        "recent_consultations": ConsultationRequest.objects.filter(
            status=ConsultationRequest.Status.NEW
        )[:4],
    }
    return render(request, "staff/staff_home.html", context)


# Thông báo Staff – lấy thông báo và tự đánh dấu đã đọc
@staff_required
def staff_notifications(request):
    notifications = Notification.objects.filter(recipient=request.staff_user)
    notifications.filter(is_read=False).update(is_read=True)
    return render(request, "staff/staff_notifications.html", {"notifications": notifications})


# Quản lý đặt phòng
@staff_required
def staff_bookings(request):
    bookings = Booking.objects.select_related("customer").all()
    status = request.GET.get("status")
    query = request.GET.get("q", "").strip()
    if status in Booking.Status.values:
        bookings = bookings.filter(status=status)
    if query:
        bookings = bookings.filter(booking_code__iexact=query)
    active_bookings = (
        Booking.objects.select_related("customer", "room")
        .exclude(status=Booking.Status.CANCELLED)
        .order_by("room_type", "check_in", "check_out")
    )
    schedule_by_type = {}
    for booking in active_bookings:
        schedule = schedule_by_type.setdefault(
            booking.room_type,
            {"name": booking.room_type, "bookings": [], "start": booking.check_in, "end": booking.check_out},
        )
        schedule["start"] = min(schedule["start"], booking.check_in)
        schedule["end"] = max(schedule["end"], booking.check_out)
        schedule["bookings"].append(booking)
    return render(
        request,
        "staff/staff_bookings.html",
        {
            "bookings": bookings,
            "active_status": status,
            "query": query,
            "room_schedule": schedule_by_type.values(),
        },
    )



# Sơ đồ phòng / Room Map
@staff_required
def staff_room_map(request):
    window_start = date.today()

    date_value = request.GET.get("date", "").strip()
    view_mode = request.GET.get("view", "week")

    if view_mode not in ("day", "week"):
        view_mode = "week"

    active_filter = request.GET.get("status", "all")

    if active_filter not in ("all", "available", "booked", "maintenance"):
        active_filter = "all"

    if date_value:
        try:
            window_start = date.fromisoformat(date_value)
        except ValueError:
            date_value = ""

    if not date_value:
        date_value = window_start.isoformat()

    window_days = 1 if view_mode == "day" else 7
    window_end = window_start + timedelta(days=window_days)

    calendar_days = [
        {
            "value": window_start + timedelta(days=offset),
            "is_today": (
                window_start + timedelta(days=offset) == date.today()
            ),
        }
        for offset in range(window_days)
    ]

    bookings_by_room = {}

    bookings = (
        Booking.objects.filter(
            check_in__lt=window_end,
            check_out__gt=window_start,
        )
        .exclude(status=Booking.Status.CANCELLED)
        .select_related("customer", "room")
        .prefetch_related("room_assignments__room")
        .order_by("check_in", "check_out")
    )

    for booking in bookings:
        assigned_room_ids = list(
            booking.room_assignments.values_list("room_id", flat=True)
        )
        if not assigned_room_ids and booking.room_id:
            assigned_room_ids = [booking.room_id]
        for room_id in assigned_room_ids:
            bookings_by_room.setdefault(room_id, []).append(booking)

    floor_groups = {}

    rooms = (
        Room.objects
        .select_related("room_type")
        .order_by("floor", "number")
    )

    for room in rooms:
        room.timeline_bookings = []

        for booking_index, booking in enumerate(
            bookings_by_room.get(room.pk, [])
        ):
            bar_start = max(booking.check_in, window_start)

            start_units = (
                bar_start - window_start
            ).days * 2

            end_units = min(
                (booking.check_out - window_start).days * 2 + 1,
                window_days * 2,
            )

            width_units = max(
                1,
                end_units - start_units
            )

            booking.bar_top = 8 + booking_index * 29

            booking.bar_position_class = (
                f"booking-left-{start_units} "
                f"booking-span-{width_units} "
                f"booking-row-{min(booking_index, 5)}"
            )

            room.timeline_bookings.append(booking)

        if room.status == Room.Status.MAINTENANCE:
            room.map_status = "maintenance"

        elif room.timeline_bookings or room.status in (
            Room.Status.BOOKED,
            Room.Status.OCCUPIED,
        ):
            room.map_status = "booked"

        else:
            room.map_status = "available"

        if (
            active_filter != "all"
            and room.map_status != active_filter
        ):
            continue

        room.timeline_height = max(
            58,
            16 + len(room.timeline_bookings) * 29
        )

        room.timeline_height_class = (
            f"timeline-height-"
            f"{min(len(room.timeline_bookings), 6)}"
        )

        floor_groups.setdefault(
            room.floor,
            []
        ).append(room)

    total_available = sum(
        1
        for r_list in floor_groups.values()
        for r in r_list
        if r.map_status == "available"
    )

    total_booked = sum(
        1
        for r_list in floor_groups.values()
        for r in r_list
        if r.map_status == "booked"
    )

    total_maintenance = sum(
        1
        for r_list in floor_groups.values()
        for r in r_list
        if r.map_status == "maintenance"
    )

    return render(
        request,
        "staff/staff_room_map.html",
        {
            "window_start": window_start,
            "window_end": window_end,
            "calendar_days": calendar_days,
            "previous_date": (
                window_start - timedelta(days=window_days)
            ).isoformat(),
            "next_date": (
                window_start + timedelta(days=window_days)
            ).isoformat(),
            "date_value": date_value,
            "view_mode": view_mode,
            "timeline_class": (
                "timeline-day"
                if view_mode == "day"
                else "timeline-week"
            ),
            "active_filter": active_filter,
            "floor_groups": floor_groups.items(),
            "total_rooms": (
                total_available
                + total_booked
                + total_maintenance
            ),
            "total_available": total_available,
            "total_booked": total_booked,
            "total_maintenance": total_maintenance,
        },
    )


# Thêm loại phòng
@staff_required
def staff_room_create(request):
    form = RoomListingForm(request.POST or None, request.FILES or None)

    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            room_type = form.save(commit=False)
            room_type.is_active = False
            room_type.listing_status = RoomType.ListingStatus.PENDING
            room_type.created_by = request.staff_user
            room_type.save()

            form.save_m2m()

            RoomPrice.objects.create(
                room_type=room_type,
                price=form.cleaned_data["price"],
                unit=form.cleaned_data["price_unit"],
                valid_from=date.today(),
            )

            prefix = form.cleaned_data["room_prefix"].strip().upper()

            for number in range(1, form.cleaned_data["quantity"] + 1):
                Room.objects.create(
                    number=f"{prefix}{number:02d}",
                    room_type=room_type,
                    floor=form.cleaned_data["floor"],
                )

            for image in form.cleaned_data["images"]:
                RoomImage.objects.create(
                    room_type=room_type,
                    image=image,
                )

        messages.success(
            request,
            "Đã đăng phòng và gửi yêu cầu Admin duyệt."
        )
        return redirect("staff-room-create")

    return render(
        request,
        "staff/staff_room_create.html",
        {"form": form},
    )
# Danh sách phòng
@staff_required
def staff_rooms(request):
    rooms = RoomType.objects.prefetch_related("rooms", "prices", "images").all()
    for room_type in rooms:
        room_type.available_quantity = (
            room_type.rooms.filter(status=Room.Status.AVAILABLE)
            .exclude(bookings__status__in=("PENDING", "CONFIRMED"))
            .distinct()
            .count()
        )
    return render(request, "staff/staff_rooms.html", {"room_types": rooms})


# Chỉnh sửa phòng
@staff_required
def staff_room_edit(request, room_type_id):
    room_type = get_object_or_404(RoomType, pk=room_type_id)
    form = RoomListingEditForm(
        request.POST or None, request.FILES or None, instance=room_type
    )
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            room_type = form.save()
            price = room_type.prices.filter(is_active=True).first()
            if price is None:
                price = RoomPrice(room_type=room_type, valid_from=timezone.localdate())
            price.price = form.cleaned_data["price"]
            price.unit = form.cleaned_data["price_unit"]
            price.save()
            rooms = list(room_type.rooms.order_by("number"))
            prefix = form.cleaned_data["room_prefix"]
            quantity = form.cleaned_data["quantity"]
            for index in range(quantity):
                number = f"{prefix}-{index + 1:02d}"
                if index < len(rooms):
                    rooms[index].number = number
                    rooms[index].floor = form.cleaned_data["floor"]
                    rooms[index].save(update_fields=("number", "floor", "updated_at"))
                else:
                    Room.objects.create(
                        number=number,
                        room_type=room_type,
                        floor=form.cleaned_data["floor"],
                    )
            for extra_room in rooms[quantity:]:
                if not extra_room.bookings.filter(
                    status__in=("PENDING", "CONFIRMED")
                ).exists():
                    extra_room.delete()
            for image in form.cleaned_data["images"]:
                RoomImage.objects.create(room_type=room_type, image=image)
            delete_ids = request.POST.getlist("delete_images")
            RoomImage.objects.filter(room_type=room_type, pk__in=delete_ids).delete()
        messages.success(request, "Đã cập nhật thông tin phòng.")
        return redirect("staff-room-edit", room_type_id=room_type.pk)
    return render(
        request, "staff/staff_room_edit.html", {"form": form, "room_type": room_type}
    )


# Chi tiết & duyệt booking
@staff_required
def staff_booking_detail(request, booking_id):
    booking = get_object_or_404(
        Booking.objects.select_related("customer", "room").prefetch_related(
            "check_in_request", "room_assignments__room"
        ),
        pk=booking_id,
    )

    form = BookingStatusForm(request.POST or None, instance=booking)

    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            locked_booking = Booking.objects.select_for_update().get(pk=booking.pk)
            assigned_rooms = list(
                locked_booking.room_assignments.select_related("room").all()
            )
            if not assigned_rooms and locked_booking.room_id:
                assigned_rooms = [None]

            locked_booking.status = form.cleaned_data["status"]
            locked_booking.notes = form.cleaned_data["notes"]
            locked_booking.save(update_fields=("status", "notes", "updated_at"))

            if locked_booking.status == Booking.Status.CONFIRMED:
                room_ids = [assignment.room_id for assignment in assigned_rooms if assignment]
                if locked_booking.room_id and not room_ids:
                    room_ids = [locked_booking.room_id]
                Room.objects.filter(pk__in=room_ids).update(status=Room.Status.BOOKED)

            if (
                locked_booking.status == Booking.Status.CANCELLED
            ):
                room_ids = [assignment.room_id for assignment in assigned_rooms if assignment]
                if locked_booking.room_id and not room_ids:
                    room_ids = [locked_booking.room_id]
                Room.objects.filter(pk__in=room_ids).update(status=Room.Status.AVAILABLE)

            if locked_booking.status == Booking.Status.CONFIRMED:
                Notification.objects.create(
                    recipient=locked_booking.customer,
                    booking=locked_booking,
                    title="Đặt phòng đã được xác nhận",
                    message=f"Booking {locked_booking.booking_code} đã được nhân viên duyệt.",
                )

        room_numbers = list(
            locked_booking.room_assignments.values_list("room__number", flat=True)
        )
        if not room_numbers and locked_booking.room:
            room_numbers = [locked_booking.room.number]
        messages.success(
            request,
            f"Đã cập nhật đơn {booking.booking_code}. Số phòng: {', '.join(room_numbers) or 'chưa gán'}.",
        )
        return redirect("staff-booking-detail", booking_id=booking.pk)

    return render(
        request,
        "staff/staff_booking_detail.html",
        {
            "booking": booking,
            "form": form,
            "check_in_request": getattr(booking, "check_in_request", None),
        },
    )


# Xử lý yêu cầu Check-in
@staff_required
def staff_checkin_request_action(request, request_id, action):
    if request.method != "POST" or action not in ("approve", "reject"):
        return redirect("staff-home")
    with transaction.atomic():
        check_in_request = get_object_or_404(
            CheckInRequest.objects.select_for_update().select_related("booking"),
            pk=request_id,
        )
        booking = Booking.objects.select_for_update().get(pk=check_in_request.booking_id)
        if check_in_request.status != CheckInRequest.Status.PENDING:
            messages.info(request, "Yêu cầu này đã được xử lý trước đó.")
        elif action == "approve" and booking.status == Booking.Status.CONFIRMED:
            if not (booking.check_in <= date.today() < booking.check_out):
                messages.error(request, "Đơn không nằm trong thời gian nhận phòng hôm nay.")
            else:
                booking.status = Booking.Status.CHECKED_IN
                booking.save(update_fields=("status", "updated_at"))
                check_in_request.status = CheckInRequest.Status.APPROVED
                check_in_request.save(update_fields=("status",))
                messages.success(request, f"Đã check-in booking {booking.booking_code}.")
        elif action == "reject" and booking.status == Booking.Status.CONFIRMED:
            check_in_request.status = CheckInRequest.Status.REJECTED
            check_in_request.reviewed_at = timezone.now()
            check_in_request.save(update_fields=("status", "reviewed_at"))
            messages.warning(request, f"Đã từ chối yêu cầu check-in {booking.booking_code}.")
        else:
            messages.error(request, "Booking không còn đủ điều kiện check-in.")
    return redirect("staff-booking-detail", booking_id=booking.pk)


# Xử lý thanh toán
@staff_required
def staff_payment_action(request, booking_id, action):
    if request.method != "POST" or action not in ("approve", "reject"):
        return redirect("staff-bookings")
    booking = get_object_or_404(Booking, pk=booking_id)
    if booking.payment_status != Booking.PaymentStatus.PENDING:
        messages.info(request, "Thanh toán này đã được xử lý hoặc chưa được khách gửi xác nhận.")
    elif action == "approve":
        mark_booking_paid(booking.pk, booking.payment_reference)
        messages.success(request, f"Đã xác nhận thanh toán đơn {booking.booking_code}.")
    else:
        booking.payment_status = Booking.PaymentStatus.REJECTED
        booking.save(update_fields=("payment_status", "updated_at"))
        messages.warning(request, f"Đã từ chối thanh toán đơn {booking.booking_code}.")
    return redirect("staff-booking-detail", booking_id=booking.pk)


# Danh sách khách hàng
@staff_required
def staff_customers(request):
    query = request.GET.get("q", "").strip()
    customers = User.objects.filter(role=User.Role.CUSTOMER)
    if query:
        customers = customers.filter(full_name__icontains=query) | customers.filter(
            phone_number__icontains=query
        )
    return render(
        request,
        "staff/staff_customers.html",
        {"customers": customers.distinct(), "query": query},
    )


# Chi tiết khách hàng
@staff_required
def staff_customer_detail(request, customer_id):
    customer = get_object_or_404(User, pk=customer_id, role=User.Role.CUSTOMER)
    form = CustomerUpdateForm(request.POST or None, instance=customer)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Đã cập nhật thông tin khách hàng.")
        return redirect("staff-customer-detail", customer_id=customer.pk)
    return render(
        request,
        "staff/staff_customer_detail.html",
        {"customer": customer, "form": form, "bookings": customer.bookings.all()[:5]},
    )


# ==========================================================
# LIVE CHAT
# ==========================================================

# Helper functions for resolving users via AreaSessionMiddleware or standard auth
def _get_current_customer(request):
    return getattr(request, 'customer_user', None) or (request.user if hasattr(request, 'user') and request.user.is_authenticated else None)

def _get_current_staff(request):
    return getattr(request, 'staff_user', None) or (request.user if hasattr(request, 'user') and request.user.is_authenticated else None)

def _get_or_create_customer_room(request):
    user = _get_current_customer(request)
    if user:
        cust_name = getattr(user, 'full_name', '') or user.get_full_name() or user.username
        cust_phone = getattr(user, 'phone_number', '')
        if not cust_phone and hasattr(user, 'profile') and hasattr(user.profile, 'phone_number'):
            cust_phone = user.profile.phone_number
        if not cust_phone:
            cust_phone = 'Chưa có'

        room, _ = ChatRoom.objects.get_or_create(
            customer=user,
            defaults={
                "customer_name": cust_name,
                "customer_phone": cust_phone
            }
        )
        if not room.customer_name or room.customer_name == "Khách vãng lai":
            room.customer_name = cust_name
        if cust_phone and cust_phone != 'Chưa có' and (not room.customer_phone or room.customer_phone == "Chưa có"):
            room.customer_phone = cust_phone
        return room

    if not request.session.session_key:
        request.session.save()
    session_key = request.session.session_key

    room, _ = ChatRoom.objects.get_or_create(
        session_key=session_key,
        defaults={
            "customer_name": "Khách vãng lai",
            "customer_phone": "Chưa có"
        }
    )
    return room


@csrf_exempt
def send_customer_chat(request):
    if request.method == "POST":
        try:
            data = json.loads(request.body)
            text = data.get("message", "").strip()
            if not text:
                return JsonResponse({"status": "error", "message": "Nội dung rỗng"}, status=400)

            user = _get_current_customer(request)
            room = _get_or_create_customer_room(request)

            # Tạo tin nhắn khách hàng và cập nhật thời gian phòng
            msg = ChatMessage.objects.create(
                room=room,
                sender=user,
                is_from_customer=True,
                message=text
            )
            room.updated_at = timezone.now()
            room.save()

            intent = parse_intent(text)
            if intent == "handoff_staff":
                room.mode = ChatRoom.Mode.STAFF
                reply_text = (
                    "Dạ, Lumina đã chuyển tin nhắn của bạn đến nhân viên. "
                    "Vui lòng chờ một lát để được phản hồi. "
                    "Nếu cần gấp, vui lòng gọi 07754169690 để được trả lời nhanh nhất."
                )
            elif intent == "fallback":
                room.mode = ChatRoom.Mode.STAFF
                reply_text = (
                    "Dạ, câu hỏi này cần nhân viên hỗ trợ thêm. Vui lòng chờ một lát, "
                    "nhân viên sẽ trả lời trong chat. Nếu cần gấp, vui lòng gọi "
                    "07754169690 để được trả lời nhanh nhất."
                )
            else:
                reply_text, _ = generate_bot_response(room, text)

            ChatMessage.objects.create(
                room=room,
                sender=None,
                is_from_customer=False,
                message=reply_text,
            )
            room.updated_at = timezone.now()
            room.save(update_fields=("mode", "updated_at"))

            # Fetch tất cả tin nhắn trong room để trả về ngay cho client
            messages = ChatMessage.objects.filter(room=room).order_by('created_at')
            msg_data = []
            for m in messages:
                msg_data.append({
                    "id": m.id,
                    "message": m.message,
                    "is_from_customer": m.is_from_customer,
                    "created_at": m.created_at.strftime("%H:%M %d/%m/%Y"),
                    "time_short": m.created_at.strftime("%H:%M %d/%m/%Y")
                })

            return JsonResponse({
                "status": "ok",
                "room_id": room.id,
                "room_mode": room.mode,
                "messages": msg_data
            })
        except Exception as e:
            return JsonResponse({"status": "error", "message": str(e)}, status=500)

    return JsonResponse({"status": "error", "message": "Method not allowed"}, status=405)


def get_customer_chat_messages(request):
    """
    API cho widget phía Khách hàng lấy danh sách tin nhắn hiện tại
    """
    room = _get_or_create_customer_room(request)

    messages = ChatMessage.objects.filter(room=room).order_by('created_at')
    msg_data = []
    for m in messages:
        msg_data.append({
            "id": m.id,
            "message": m.message,
            "is_from_customer": m.is_from_customer,
            "created_at": m.created_at.strftime("%H:%M %d/%m/%Y"),
            "time_short": m.created_at.strftime("%H:%M %d/%m/%Y")
        })

    return JsonResponse({
        "status": "ok",
        "room_id": room.id,
        "room_mode": room.mode,
        "messages": msg_data
    })


@staff_required
def staff_consultations(request, room_id=None):
    rooms = (
        ChatRoom.objects.filter(messages__isnull=False)
        .distinct()
        .order_by("-updated_at")
    )

    active_room = None
    messages_list = []

    if room_id:
        active_room = get_object_or_404(ChatRoom, id=room_id)
    elif rooms.exists():
        active_room = rooms.first()

    if active_room:
        messages_list = ChatMessage.objects.filter(room=active_room).order_by('created_at')

    if request.method == "POST" and active_room:
        action = request.POST.get("action", "")
        if action == "toggle_mode":
            new_mode = request.POST.get("mode", "")
            if new_mode in [ChatRoom.Mode.BOT, ChatRoom.Mode.STAFF]:
                active_room.mode = new_mode
                active_room.save(update_fields=['mode', 'updated_at'])
                if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                    return JsonResponse({"status": "ok", "mode": active_room.mode})
                return redirect('staff-consultations-detail', room_id=active_room.id)

        reply_text = request.POST.get("message", "").strip()
        if reply_text:
            staff_user = _get_current_staff(request)
            ChatMessage.objects.create(
                room=active_room,
                sender=staff_user,
                is_from_customer=False,
                message=reply_text
            )
            # Khi nhân viên nhắn tin trả lời, giữ hoặc đảm bảo phòng ở chế độ STAFF
            active_room.mode = ChatRoom.Mode.STAFF
            active_room.updated_at = timezone.now()
            active_room.save()

            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({"status": "ok"})

            return redirect('staff-consultations-detail', room_id=active_room.id)

    return render(request, 'staff/staff_consultations.html', {
        'rooms': rooms,
        'active_room': active_room,
        'messages': messages_list,
    })


@staff_required
def api_get_room_messages(request, room_id):
    """
    API cho màn hình Nhân viên tự động fetch tin nhắn mới theo room_id
    """
    room = get_object_or_404(ChatRoom, id=room_id)
    messages = ChatMessage.objects.filter(room=room).order_by('created_at')

    msg_data = []
    for m in messages:
        sender_name = ""
        if m.is_from_customer:
            sender_name = room.display_name
        else:
            if m.sender:
                sender_name = getattr(m.sender, 'full_name', '') or m.sender.get_full_name() or m.sender.username
            else:
                sender_name = "Lumina Chatbot 🤖" if room.mode == ChatRoom.Mode.BOT else "Nhân viên"

        msg_data.append({
            "id": m.id,
            "message": m.message,
            "is_from_customer": m.is_from_customer,
            "sender_name": sender_name,
            "created_at": m.created_at.strftime("%H:%M %d/%m/%Y")
        })

    return JsonResponse({
        "status": "ok",
        "room_id": room.id,
        "room_mode": room.mode,
        "customer_name": room.display_name,
        "customer_phone": room.display_phone,
        "messages": msg_data
    })

