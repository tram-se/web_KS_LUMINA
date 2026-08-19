from django.urls import path

from .auth import staff_login, staff_logout
from .views import (
    staff_booking_detail,
    staff_bookings,
    staff_consultation_detail,
    staff_consultations,
    staff_customer_detail,
    staff_customers,
    staff_home,
)

urlpatterns = [
    path("staff/dang-nhap/", staff_login, name="staff-login"),
    path("staff/dang-xuat/", staff_logout, name="staff-logout"),
    path("staff/", staff_home, name="staff-home"),
    path("staff/dat-phong/", staff_bookings, name="staff-bookings"),
    path(
        "staff/dat-phong/<int:booking_id>/",
        staff_booking_detail,
        name="staff-booking-detail",
    ),
    path("staff/khach-hang/", staff_customers, name="staff-customers"),
    path(
        "staff/khach-hang/<int:customer_id>/",
        staff_customer_detail,
        name="staff-customer-detail",
    ),
    path("staff/tu-van/", staff_consultations, name="staff-consultations"),
    path(
        "staff/tu-van/<int:consultation_id>/",
        staff_consultation_detail,
        name="staff-consultation-detail",
    ),
]
