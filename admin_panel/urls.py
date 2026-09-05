from django.urls import path

from .views import admin_booking_report, admin_bulk_approve, admin_home

urlpatterns = [
    path("admin-panel/", admin_home, name="admin-home"),
    path(
        "admin-panel/bao-cao-dat-phong/",
        admin_booking_report,
        name="admin-booking-report",
    ),
    path(
        "admin-panel/duyet-don-hang-loat/",
        admin_bulk_approve,
        name="admin-bulk-approve",
    ),
]
