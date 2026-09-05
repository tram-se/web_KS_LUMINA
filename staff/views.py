from django.contrib import messages
from django.db import transaction
from django.utils import timezone
from django.shortcuts import get_object_or_404, redirect, render

from accounts.decorators import staff_required
from accounts.models import Booking, CheckInRequest, ConsultationRequest, User
from admin_panel.models import Room, RoomImage, RoomPrice, RoomType

from .forms import (
    BookingStatusForm,
    ConsultationStatusForm,
    CustomerUpdateForm,
    RoomListingForm,
    RoomListingEditForm,
)


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


@staff_required
def staff_bookings(request):
    bookings = Booking.objects.select_related("customer").all()
    status = request.GET.get("status")
    query = request.GET.get("q", "").strip()
    if status in Booking.Status.values:
        bookings = bookings.filter(status=status)
    if query:
        bookings = bookings.filter(booking_code__iexact=query)
    return render(
        request,
        "staff/staff_bookings.html",
        {"bookings": bookings, "active_status": status, "query": query},
    )


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
                valid_from=timezone.localdate(),
            )
            prefix = form.cleaned_data["room_prefix"].strip().upper()
            for number in range(1, form.cleaned_data["quantity"] + 1):
                Room.objects.create(
                    number=f"{prefix}-{number:02d}",
                    room_type=room_type,
                    floor=form.cleaned_data["floor"],
                )
            for image in form.cleaned_data["images"]:
                RoomImage.objects.create(room_type=room_type, image=image)
        messages.success(request, "Đã đăng phòng và gửi yêu cầu Admin duyệt.")
        return redirect("staff-room-create")
    return render(request, "staff/staff_room_create.html", {"form": form})


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


@staff_required
def staff_booking_detail(request, booking_id):
    booking = get_object_or_404(
        Booking.objects.select_related("customer", "room").prefetch_related("check_in_request"), pk=booking_id
    )
    form = BookingStatusForm(request.POST or None, instance=booking)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            locked_booking = Booking.objects.select_for_update().get(pk=booking.pk)
            selected_room = form.cleaned_data.get("room")
            if form.cleaned_data["status"] == Booking.Status.CONFIRMED:
                room_is_free = not selected_room.bookings.filter(
                    status__in=(Booking.Status.PENDING, Booking.Status.CONFIRMED),
                    check_in__lt=locked_booking.check_out,
                    check_out__gt=locked_booking.check_in,
                ).exists()
                if not room_is_free:
                    form.add_error(
                        "room", "Phòng vừa được gán cho đơn khác trong khoảng này."
                    )
                    return render(
                        request,
                        "staff/staff_booking_detail.html",
                        {"booking": booking, "form": form},
                    )
            locked_booking.status = form.cleaned_data["status"]
            locked_booking.room = selected_room
            locked_booking.notes = form.cleaned_data["notes"]
            locked_booking.save(update_fields=("status", "room", "notes", "updated_at"))
        room_number = selected_room.number if selected_room else "chưa gán"
        messages.success(
            request,
            f"Đã cập nhật đơn {booking.booking_code}. Số phòng: {room_number}.",
        )
        return redirect("staff-booking-detail", booking_id=booking.pk)
    return render(
        request,
        "staff/staff_booking_detail.html",
        {"booking": booking, "form": form, "check_in_request": getattr(booking, "check_in_request", None)},
    )


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
            if not (booking.check_in <= timezone.localdate() < booking.check_out):
                messages.error(request, "Đơn không nằm trong thời gian nhận phòng hôm nay.")
            else:
                booking.status = Booking.Status.CHECKED_IN
                booking.save(update_fields=("status", "updated_at"))
                check_in_request.status = CheckInRequest.Status.APPROVED
                check_in_request.reviewed_at = timezone.now()
                check_in_request.save(update_fields=("status", "reviewed_at"))
                messages.success(request, f"Đã check-in booking {booking.booking_code}.")
        elif action == "reject" and booking.status == Booking.Status.CONFIRMED:
            check_in_request.status = CheckInRequest.Status.REJECTED
            check_in_request.reviewed_at = timezone.now()
            check_in_request.save(update_fields=("status", "reviewed_at"))
            messages.warning(request, f"Đã từ chối yêu cầu check-in {booking.booking_code}.")
        else:
            messages.error(request, "Booking không còn đủ điều kiện check-in.")
    return redirect("staff-booking-detail", booking_id=booking.pk)


@staff_required
def staff_payment_action(request, booking_id, action):
    if request.method != "POST" or action not in ("approve", "reject"):
        return redirect("staff-bookings")
    booking = get_object_or_404(Booking, pk=booking_id)
    if booking.payment_status != Booking.PaymentStatus.PENDING:
        messages.info(request, "Thanh toán này đã được xử lý hoặc chưa được khách gửi xác nhận.")
    elif action == "approve":
        booking.payment_status = Booking.PaymentStatus.PAID
        booking.paid_at = timezone.now()
        booking.save(update_fields=("payment_status", "paid_at", "updated_at"))
        messages.success(request, f"Đã xác nhận thanh toán đơn {booking.booking_code}.")
    else:
        booking.payment_status = Booking.PaymentStatus.REJECTED
        booking.save(update_fields=("payment_status", "updated_at"))
        messages.warning(request, f"Đã từ chối thanh toán đơn {booking.booking_code}.")
    return redirect("staff-booking-detail", booking_id=booking.pk)


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


@staff_required
def staff_consultations(request):
    consultations = ConsultationRequest.objects.all()
    return render(
        request, "staff/staff_consultations.html", {"consultations": consultations}
    )


@staff_required
def staff_consultation_detail(request, consultation_id):
    consultation = get_object_or_404(ConsultationRequest, pk=consultation_id)
    form = ConsultationStatusForm(request.POST or None, instance=consultation)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Đã cập nhật yêu cầu tư vấn.")
        return redirect("staff-consultation-detail", consultation_id=consultation.pk)
    return render(
        request,
        "staff/staff_consultation_detail.html",
        {"consultation": consultation, "form": form},
    )
