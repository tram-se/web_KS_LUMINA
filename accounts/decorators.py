from functools import wraps

from django.contrib import messages
from django.contrib.auth.views import redirect_to_login
from django.shortcuts import redirect

from .models import User


def role_required(*allowed_roles):
    def decorator(view_func):
        @wraps(view_func)
        def wrapped(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect_to_login(request.get_full_path())
            if request.user.role not in allowed_roles:
                messages.error(request, "Bạn không có quyền truy cập trang này.")
                return redirect("dashboard")
            return view_func(request, *args, **kwargs)

        return wrapped

    return decorator


def area_role_required(area, role):
    def decorator(view_func):
        @wraps(view_func)
        def wrapped(request, *args, **kwargs):
            user = getattr(request, f"{area}_user", None)
            if user is None:
                login_url = "/staff/dang-nhap/" if area == "staff" else "/dang-nhap/"
                return redirect_to_login(request.get_full_path(), login_url=login_url)
            if user.role != role:
                messages.error(request, "Bạn không có quyền truy cập trang này.")
                return redirect("dashboard")
            return view_func(request, *args, **kwargs)

        return wrapped

    return decorator


customer_required = area_role_required("customer", User.Role.CUSTOMER)
staff_required = area_role_required("staff", User.Role.STAFF)
admin_required = role_required(User.Role.ADMIN)
