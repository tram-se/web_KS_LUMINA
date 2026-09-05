from django.contrib import messages
from django.contrib.auth import authenticate
from django.contrib.auth.forms import AuthenticationForm
from django.shortcuts import redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import ensure_csrf_cookie

from accounts.models import User

from .forms import StaffRegistrationForm


@never_cache
@ensure_csrf_cookie
def staff_login(request):
    form = AuthenticationForm(request, data=request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = authenticate(
            request,
            username=form.cleaned_data["username"],
            password=form.cleaned_data["password"],
        )
        if user and user.role == User.Role.STAFF and user.is_active:
            request.session.cycle_key()
            request.session["staff_user_id"] = user.pk
            messages.success(request, "Đăng nhập khu vực Staff thành công.")
            return redirect("staff-home")
        form.add_error(None, "Tài khoản này không thuộc khu vực Staff.")
    return render(request, "accounts/login.html", {"form": form, "login_area": "Staff"})


def staff_register(request):
    form = StaffRegistrationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        request.session.cycle_key()
        request.session["staff_user_id"] = user.pk
        messages.success(request, "Đăng ký tài khoản Staff thành công.")
        return redirect("staff-home")
    return render(request, "accounts/staff_register.html", {"form": form})


def staff_logout(request):
    if request.method == "POST":
        request.session.pop("staff_user_id", None)
        return redirect("staff-login")
    return render(
        request,
        "accounts/logout.html",
        {"logout_area": "Staff", "cancel_url": "/staff/"},
    )
