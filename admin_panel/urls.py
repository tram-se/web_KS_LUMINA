from django.urls import path

from .views import admin_home

urlpatterns = [
    path("admin-panel/", admin_home, name="admin-home"),
]
