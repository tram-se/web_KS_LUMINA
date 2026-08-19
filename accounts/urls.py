from django.urls import path

from .views import customer_home, customer_login, customer_logout, dashboard, register

urlpatterns = [
    path("dang-nhap/", customer_login, name="login"),
    path("dang-ky/", register, name="register"),
    path("dang-xuat/", customer_logout, name="logout"),
    path("dashboard/", dashboard, name="dashboard"),
    path("customer/", customer_home, name="customer-home"),
]
