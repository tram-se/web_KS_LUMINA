import calendar
from datetime import date

from django.contrib import messages
from django.db import transaction
from django.db.models import Q, Sum
from django.shortcuts import redirect, render

from accounts.decorators import admin_required
from accounts.models import Booking, User

from .models import ActivityLog, Amenity, Room, RoomPrice, RoomType, Service

#Trang tổng quan Admin
@admin_required
def admin_home(request):
    context = {
        "user_count": User.objects.count(),
        "customer_count": User.objects.filter(role=User.Role.CUSTOMER).count(),
        "staff_count": User.objects.filter(role=User.Role.STAFF).count(),
        "booking_count": Booking.objects.count(),
        "pending_bookings": Booking.objects.filter(
            status=Booking.Status.PENDING
        ).count(),
        "room_count": Room.objects.count(),
        "available_rooms": Room.objects.filter(status=Room.Status.AVAILABLE).count(),
        "maintenance_rooms": Room.objects.filter(
            status=Room.Status.MAINTENANCE
        ).count(),
        "room_type_count": RoomType.objects.count(),
        "pending_room_listings": RoomType.objects.filter(
            listing_status=RoomType.ListingStatus.PENDING
        ).count(),
        "price_count": RoomPrice.objects.filter(is_active=True).count(),
        "amenity_count": Amenity.objects.filter(is_active=True).count(),
        "service_count": Service.objects.filter(is_active=True).count(),
        "recent_activity": ActivityLog.objects.select_related("actor")[:8],
        "recent_bookings": Booking.objects.select_related("customer")[:5],
        "room_statuses": Room.Status.choices,
    }
    return render(request, "admin_panel/admin_home.html", context)


def _month_bounds(request):
    today = date.today()
    try:
        year = int(request.GET.get("year", today.year))
        month = int(request.GET.get("month", today.month))
        selected = date(year, month, 1)
    except (TypeError, ValueError):
        selected = date(today.year, today.month, 1)
    return selected, date(
        selected.year,
        selected.month,
        calendar.monthrange(selected.year, selected.month)[1],
    )


@admin_required
def admin_booking_report(request):
    month_start, month_end = _month_bounds(request)
    month_end_exclusive = date(
        month_end.year + (month_end.month == 12),
        1 if month_end.month == 12 else month_end.month + 1,
        1,
    )
    bookings = Booking.objects.select_related("customer", "room").filter(
        check_in__lt=month_end_exclusive,
        check_out__gt=month_start,
    )
    non_cancelled = bookings.exclude(status=Booking.Status.CANCELLED)
    confirmed = bookings.filter(status=Booking.Status.CONFIRMED)
    total_rooms = Room.objects.filter(status=Room.Status.AVAILABLE).count()
    booked_rooms = confirmed.filter(
        room__isnull=False
    ).filter(
        check_in__lt=month_end_exclusive,
        check_out__gt=month_start,
    ).values("room_id").distinct().count()
    available_rooms = max(total_rooms - booked_rooms, 0)
    revenue_expected = non_cancelled.aggregate(total=Sum("total_price"))["total"] or 0
    revenue_actual = confirmed.aggregate(total=Sum("total_price"))["total"] or 0
    daily_stats = []
    for day in range(1, month_end.day + 1):
        current_day = date(month_start.year, month_start.month, day)
        day_bookings = bookings.filter(check_in=current_day)
        daily_stats.append(
            {
                "day": day,
                "count": day_bookings.count(),
                "revenue": day_bookings.exclude(
                    status=Booking.Status.CANCELLED
                ).aggregate(total=Sum("total_price"))["total"]
                or 0,
            }
        )
    context = {
        "bookings": bookings,
        "month_start": month_start,
        "month_end": month_end,
        "total_bookings": bookings.count(),
        "revenue_expected": revenue_expected,
        "revenue_actual": revenue_actual,
        "total_rooms": total_rooms,
        "booked_rooms": booked_rooms,
        "available_rooms": available_rooms,
        "occupancy_rate": (
            round(booked_rooms / total_rooms * 100, 1) if total_rooms else 0
        ),
        "pending_count": bookings.filter(status=Booking.Status.PENDING).count(),
        "confirmed_count": bookings.filter(status=Booking.Status.CONFIRMED).count(),
        "cancelled_count": bookings.filter(status=Booking.Status.CANCELLED).count(),
        "daily_stats": daily_stats,
    }
    return render(request, "admin_panel/booking_report.html", context)


@admin_required
def admin_bulk_approve(request):
    pending = Booking.objects.filter(status=Booking.Status.PENDING).order_by(
        "check_in", "created_at"
    )
    room_type_name = request.GET.get("room_type", "")
    if room_type_name:
        pending = pending.filter(room_type=room_type_name)
    if request.method == "POST":
        selected_ids = request.POST.getlist("booking_ids")
        approved = 0
        skipped = 0
        with transaction.atomic():
            for booking_id in selected_ids:
                booking = (
                    Booking.objects.select_for_update()
                    .filter(pk=booking_id, status=Booking.Status.PENDING)
                    .first()
                )
                if not booking:
                    continue
                room = (
                    Room.objects.select_for_update()
                    .filter(
                        room_type__name=booking.room_type,
                        status=Room.Status.AVAILABLE,
                    )
                    .exclude(
                        bookings__status__in=(
                            Booking.Status.PENDING,
                            Booking.Status.CONFIRMED,
                        ),
                        bookings__check_in__lt=booking.check_out,
                        bookings__check_out__gt=booking.check_in,
                    )
                    .distinct()
                    .first()
                )
                if not room:
                    skipped += 1
                    continue
                booking.status = Booking.Status.CONFIRMED
                booking.room = room
                booking.save(update_fields=("status", "room", "updated_at"))
                ActivityLog.objects.create(
                    action=f"Duyệt hàng loạt đơn {booking.booking_code} - phòng {room.number}",
                    actor=request.user,
                    level=ActivityLog.Level.SUCCESS,
                )
                approved += 1
        messages.success(
            request, f"Đã duyệt {approved} đơn; {skipped} đơn không đủ phòng."
        )
        return redirect("admin-bulk-approve")
    room_types = RoomType.objects.filter(name__in=pending.values("room_type")).order_by(
        "name"
    )
    return render(
        request,
        "admin_panel/bulk_approve.html",
        {
            "bookings": pending,
            "room_types": room_types,
            "active_room_type": room_type_name,
        },
    )
