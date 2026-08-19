from django.shortcuts import render

from accounts.decorators import admin_required
from accounts.models import Booking, User

from .models import ActivityLog, Amenity, Room, RoomPrice, RoomType, Service


@admin_required
def admin_home(request):
    context = {
        "user_count": User.objects.count(),
        "customer_count": User.objects.filter(role=User.Role.CUSTOMER).count(),
        "staff_count": User.objects.filter(role=User.Role.STAFF).count(),
        "booking_count": Booking.objects.count(),
        "pending_bookings": Booking.objects.filter(status=Booking.Status.PENDING).count(),
        "room_count": Room.objects.count(),
        "available_rooms": Room.objects.filter(status=Room.Status.AVAILABLE).count(),
        "maintenance_rooms": Room.objects.filter(status=Room.Status.MAINTENANCE).count(),
        "room_type_count": RoomType.objects.count(),
        "price_count": RoomPrice.objects.filter(is_active=True).count(),
        "amenity_count": Amenity.objects.filter(is_active=True).count(),
        "service_count": Service.objects.filter(is_active=True).count(),
        "recent_activity": ActivityLog.objects.select_related("actor")[:8],
        "recent_bookings": Booking.objects.select_related("customer")[:5],
        "room_statuses": Room.Status.choices,
    }
    return render(request, "admin_panel/admin_home.html", context)
