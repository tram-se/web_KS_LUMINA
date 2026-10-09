from datetime import date

from django.contrib import admin
from django.contrib import messages
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.db import transaction
from django.db.models import Q, Sum
from django.http import HttpRequest
from django.urls import reverse
from django.utils.html import format_html

from admin_panel.models import ActivityLog, Room

from .models import Booking, ConsultationRequest, User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = (
        "username",
        "full_name",
        "email",
        "phone_number",
        "role",
        "is_active",
        "created_at",
    )
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
    change_list_template = "admin/accounts/booking/danh_sach_thay_doi.html"
    actions = ("approve_selected_bookings",)
    list_display = (
        "booking_code",
        "guest_name",
        "guest_phone",
        "guest_id_number",
        "room_type",
        "assigned_room",
        "check_in",
        "check_out",
        "status",
        "quick_edit",
    )
    list_filter = ("status", "room_type", "check_in")
    search_fields = (
        "booking_code",
        "guest_full_name",
        "guest_phone",
        "guest_id_number",
        "customer__full_name",
        "customer__phone_number",
        "room_type",
        "room__number",
    )
    autocomplete_fields = ("customer", "room")
    date_hierarchy = "check_in"

    @admin.display(description="Họ tên khách", ordering="guest_full_name")
    def guest_name(self, obj):
        return obj.guest_full_name or obj.customer.full_name

    @admin.display(description="SĐT", ordering="guest_phone")
    def guest_phone(self, obj):
        return obj.guest_phone or obj.customer.phone_number or "-"

    @admin.display(description="Phòng gán", ordering="room__number")
    def assigned_room(self, obj):
        return obj.room.number if obj.room else "Chưa gán"

    @admin.display(description="Thao tác")
    def quick_edit(self, obj):
        url = reverse("admin:accounts_booking_change", args=(obj.pk,))
        return format_html('<a class="button" href="{}">Mở đơn</a>', url)

    def _selected_month(self, request):
        today = date.today()
        try:
            year = int(request.GET.get("year", today.year))
            month = int(request.GET.get("month", today.month))
            return date(year, month, 1)
        except (TypeError, ValueError):
            return date(today.year, today.month, 1)

    def get_queryset(self, request):
        queryset = super().get_queryset(request).select_related("customer", "room")
        month_start = self._selected_month(request)
        month_end = date(
            month_start.year + (month_start.month == 12),
            1 if month_start.month == 12 else month_start.month + 1,
            1,
        )
        if request.GET.get("month") or request.GET.get("year"):
            queryset = queryset.filter(
                check_in__gte=month_start, check_in__lt=month_end
            )
        return queryset

    def changelist_view(self, request, extra_context=None):
        month_start = self._selected_month(request)
        month_end = date(
            month_start.year + (month_start.month == 12),
            1 if month_start.month == 12 else month_start.month + 1,
            1,
        )
        month_bookings = Booking.objects.filter(
            check_in__gte=month_start, check_in__lt=month_end
        )
        context = {
            "report_month": month_start,
            "report_total": month_bookings.count(),
            "report_revenue": month_bookings.exclude(
                status=Booking.Status.CANCELLED
            ).aggregate(total=Sum("total_price"))["total"]
            or 0,
            "report_pending": month_bookings.filter(
                status=Booking.Status.PENDING
            ).count(),
            "report_confirmed": month_bookings.filter(
                status=Booking.Status.CONFIRMED
            ).count(),
            "report_cancelled": month_bookings.filter(
                status=Booking.Status.CANCELLED
            ).count(),
            "report_month_end": month_end,
        }
        if extra_context:
            context.update(extra_context)
        return super().changelist_view(request, extra_context=context)

    @admin.action(description="Duyệt các đơn đã chọn")
    def approve_selected_bookings(self, request: HttpRequest, queryset):
        approved = 0
        skipped = 0
        with transaction.atomic():
            for booking_id in queryset.filter(
                status=Booking.Status.PENDING
            ).values_list("pk", flat=True):
                booking = Booking.objects.select_for_update().get(pk=booking_id)
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
                if room is None:
                    skipped += 1
                    continue
                booking.status = Booking.Status.CONFIRMED
                booking.room = room
                booking.save(update_fields=("status", "room", "updated_at"))
                ActivityLog.objects.create(
                    action=f"Admin duyệt đơn {booking.booking_code}, gán phòng {room.number}",
                    actor=request.user,
                    level=ActivityLog.Level.SUCCESS,
                )
                approved += 1
        if approved:
            self.message_user(
                request,
                f"Đã duyệt {approved} đơn và gán phòng thành công.",
                messages.SUCCESS,
            )
        if skipped:
            self.message_user(
                request,
                f"Có {skipped} đơn chưa duyệt vì không còn phòng phù hợp.",
                messages.WARNING,
            )


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
