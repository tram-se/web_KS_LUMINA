from django.urls import path

# Import thêm send_customer_chat và get_customer_chat_messages từ staff.views
from staff.views import send_customer_chat, get_customer_chat_messages

from .views import (
    customer_home,
    customer_booking_detail,
    booking_qr,
    booking_qr_scan,
    customer_login,
    customer_logout,
    dashboard,
    register,
    customer_profile,
    room_detail,
    room_list,
    booking_payment,
    booking_invoice,
    booking_payment_result,
    booking_payment_qr,
    payment_qr_scan,
    booking_payment_status,
    bank_payment_webhook,
    momo_ipn,
    customer_notifications,
    customer_consultation,
)

urlpatterns = [
    path("", customer_home, name="customer-home"),
    path("dang-nhap/", customer_login, name="login"),
    path("dang-ky/", register, name="register"),
    path("dang-xuat/", customer_logout, name="logout"),
    path("dashboard/", dashboard, name="dashboard"),
    path("customer/", customer_home),
    path("customer/tai-khoan/", customer_profile, name="customer-profile"),
    path("customer/thong-bao/", customer_notifications, name="customer-notifications"),
    path(
        "customer/dat-phong/<int:booking_id>/",
        customer_booking_detail,
        name="customer-booking-detail",
    ),
    path("customer/dat-phong/<int:booking_id>/qr/", booking_qr, name="booking-qr"),
    path("booking/qr/<str:token>/", booking_qr_scan, name="booking-qr-scan"),
    path("customer/phong/", room_list, name="room-list"),
    path("customer/phong/<int:room_id>/", room_detail, name="room-detail"),
    path("customer/dat-phong/<int:booking_id>/thanh-toan/", booking_payment, name="booking-payment"),
    path("customer/dat-phong/<int:booking_id>/thanh-toan/qr/", booking_payment_qr, name="booking-payment-qr"),
    path("thanh-toan/qr/<str:token>/", payment_qr_scan, name="payment-qr-scan"),
    path("dat-phong/<int:booking_id>/hoa-don/", booking_invoice, name="booking-invoice"),
    path("thanh-toan/momo/ket-qua/<int:booking_id>/", booking_payment_result, name="booking-payment-result"),
    path("thanh-toan/momo/ipn/", momo_ipn, name="momo-ipn"),
    path("thanh-toan/trang-thai/<int:booking_id>/", booking_payment_status, name="booking-payment-status"),
    path("thanh-toan/webhook/", bank_payment_webhook, name="bank-payment-webhook"),
    path(
        "customer/tu-van/",
        customer_consultation,
        name="customer-consultation",
    ),
    # THÊM ĐƯỜNG DẪN API CHAT TẠI ĐÂY
    path("api/send-chat/", send_customer_chat, name="send-customer-chat"),
    path("api/get-chat/", get_customer_chat_messages, name="get-customer-chat"),
]