from django.db import transaction
from django.utils import timezone

from admin_panel.models import Room

from .models import Booking, Notification, User


@transaction.atomic
def mark_booking_paid(booking_id, payment_reference=""):
    booking = Booking.objects.select_for_update().select_related("customer", "room").get(
        pk=booking_id
    )
    if booking.payment_status == Booking.PaymentStatus.PAID:
        return booking, False

    booking.payment_status = Booking.PaymentStatus.PAID
    booking.payment_reference = payment_reference or booking.payment_reference
    booking.paid_at = timezone.now()
    update_fields = ["payment_status", "paid_at", "updated_at"]
    if payment_reference:
        update_fields.append("payment_reference")

    if booking.status == Booking.Status.PENDING:
        booking.status = Booking.Status.CONFIRMED
        update_fields.append("status")
    booking.save(update_fields=update_fields)

    assigned_room_ids = list(
        booking.room_assignments.values_list("room_id", flat=True)
    )
    if not assigned_room_ids and booking.room_id:
        assigned_room_ids = [booking.room_id]
    Room.objects.filter(pk__in=assigned_room_ids).exclude(
        status=Room.Status.OCCUPIED
    ).update(status=Room.Status.BOOKED)

    staff_users = User.objects.filter(
        role__in=(User.Role.STAFF, User.Role.ADMIN), is_active=True
    )
    Notification.objects.bulk_create(
        [
            Notification(
                recipient=staff_user,
                booking=booking,
                title="Đã nhận thanh toán tự động",
                message=f"Booking {booking.booking_code} đã thanh toán đủ {booking.total_price:,.0f} VND.",
            )
            for staff_user in staff_users
        ]
    )
    Notification.objects.create(
        recipient=booking.customer,
        booking=booking,
        title="Thanh toán thành công",
        message=f"Booking {booking.booking_code} đã được xác nhận sau khi nhận đủ tiền.",
    )
    return booking, True