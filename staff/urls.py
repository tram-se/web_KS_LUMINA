from django.urls import path

from .auth import staff_login, staff_logout, staff_register
from .views import (
    staff_booking_detail,
    staff_bookings,
    staff_customer_detail,
    staff_customers,
    staff_home,
    staff_room_create,
    staff_room_map,
    staff_room_edit,
    staff_rooms,
    staff_checkin_request_action,
    staff_payment_action,
    staff_notifications,
    staff_consultations,
    send_customer_chat,
    api_get_room_messages,
)

urlpatterns = [
    path("staff/dang-nhap/", staff_login, name="staff-login"),
    path("staff/dang-ky/", staff_register, name="staff-register"),
    path("staff/dang-xuat/", staff_logout, name="staff-logout"),
    path("staff/", staff_home, name="staff-home"),
    path("staff/thong-bao/", staff_notifications, name="staff-notifications"),
    path("staff/dat-phong/", staff_bookings, name="staff-bookings"),
    path("staff/so-do-phong/", staff_room_map, name="staff-room-map"),
    path("staff/dang-phong/", staff_room_create, name="staff-room-create"),
    path("staff/phong-da-dang/", staff_rooms, name="staff-rooms"),
    path(
        "staff/phong-da-dang/<int:room_type_id>/sua/",
        staff_room_edit,
        name="staff-room-edit",
    ),
    path(
        "staff/dat-phong/<int:booking_id>/",
        staff_booking_detail,
        name="staff-booking-detail",
    ),
    path(
        "staff/check-in-requests/<int:request_id>/<str:action>/",
        staff_checkin_request_action,
        name="staff-checkin-request-action",
    ),
    path(
        "staff/thanh-toan/<int:booking_id>/<str:action>/",
        staff_payment_action,
        name="staff-payment-action",
    ),
    path("staff/khach-hang/", staff_customers, name="staff-customers"),
    path(
        "staff/khach-hang/<int:customer_id>/",
        staff_customer_detail,
        name="staff-customer-detail",
    ),

    # --- KHU VỰC TƯ VẤN & LIVE CHAT ---
    path("staff/tu-van/", staff_consultations, name="staff-consultations"),
    path(
        "staff/tu-van/<int:room_id>/",
        staff_consultations,
        name="staff-consultations-detail",
    ),

    # API nhận tin nhắn từ widget của khách
    path("api/send-chat/", send_customer_chat, name="api-send-chat"),
    path("api/staff/chat/<int:room_id>/", api_get_room_messages, name="api-staff-room-messages"),
]