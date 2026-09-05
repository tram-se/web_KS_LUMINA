from django.urls import path

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
    momo_ipn,
)

urlpatterns = [
    path("", dashboard),
    path("dang-nhap/", customer_login, name="login"),
    path("dang-ky/", register, name="register"),
    path("dang-xuat/", customer_logout, name="logout"),
    path("dashboard/", dashboard, name="dashboard"),
    path("customer/", customer_home, name="customer-home"),
    path("customer/tai-khoan/", customer_profile, name="customer-profile"),
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
    path("dat-phong/<int:booking_id>/hoa-don/", booking_invoice, name="booking-invoice"),
    path("thanh-toan/momo/ket-qua/<int:booking_id>/", booking_payment_result, name="booking-payment-result"),
    path("thanh-toan/momo/ipn/", momo_ipn, name="momo-ipn"),
]
