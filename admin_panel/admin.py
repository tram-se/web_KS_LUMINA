from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from accounts.models import Booking, ConsultationRequest, User

from .models import ActivityLog, Amenity, Room, RoomPrice, RoomType, Service


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ("username", "full_name", "email", "role", "is_active", "created_at")
    list_filter = ("role", "is_active", "is_staff")
    search_fields = ("username", "full_name", "email", "phone_number")
    fieldsets = BaseUserAdmin.fieldsets + (
        (
            "Lumina profile",
            {"fields": ("full_name", "phone_number", "role", "created_at")},
        ),
    )
    readonly_fields = ("created_at",)
    add_fieldsets = BaseUserAdmin.add_fieldsets + (
        ("Lumina profile", {"fields": ("full_name", "email", "phone_number", "role")}),
    )


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = (
        "booking_code",
        "customer",
        "room_type",
        "check_in",
        "check_out",
        "status",
        "created_at",
    )
    list_filter = ("status", "room_type")
    search_fields = ("booking_code", "customer__full_name", "customer__phone_number")
    autocomplete_fields = ("customer",)


@admin.register(ConsultationRequest)
class ConsultationRequestAdmin(admin.ModelAdmin):
    list_display = (
        "full_name",
        "phone_number",
        "preferred_room",
        "status",
        "created_at",
    )
    list_filter = ("status",)
    search_fields = ("full_name", "phone_number")


@admin.register(RoomType)
class RoomTypeAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "max_guests", "area_sqm", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name", "code")


@admin.register(Room)
class RoomAdmin(admin.ModelAdmin):
    list_display = ("number", "room_type", "floor", "status", "updated_at")
    list_filter = ("status", "room_type")
    search_fields = ("number", "room_type__name")
    autocomplete_fields = ("room_type",)


@admin.register(RoomPrice)
class RoomPriceAdmin(admin.ModelAdmin):
    list_display = ("room_type", "price", "valid_from", "valid_to", "is_active")
    list_filter = ("is_active", "room_type")
    autocomplete_fields = ("room_type",)


@admin.register(Amenity)
class AmenityAdmin(admin.ModelAdmin):
    list_display = ("name", "description", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name",)


@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    list_display = ("name", "price", "unit", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name",)


@admin.register(ActivityLog)
class ActivityLogAdmin(admin.ModelAdmin):
    list_display = ("action", "actor", "level", "created_at")
    list_filter = ("level", "created_at")
    search_fields = ("action", "actor__full_name")
    readonly_fields = ("created_at",)
