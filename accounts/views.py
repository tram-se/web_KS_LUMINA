from django.contrib import messages
from django.contrib.auth import authenticate
from django.contrib.auth.forms import AuthenticationForm
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import ensure_csrf_cookie
from django.shortcuts import redirect, render

from .decorators import customer_required
from .models import User
from .forms import CustomerRegistrationForm


@never_cache
@ensure_csrf_cookie
def customer_login(request):
    form = AuthenticationForm(request, data=request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = authenticate(
            request,
            username=form.cleaned_data["username"],
            password=form.cleaned_data["password"],
        )
        if user and user.role == User.Role.CUSTOMER and user.is_active:
            request.session.cycle_key()
            request.session["customer_user_id"] = user.pk
            messages.success(request, "Đăng nhập khu vực khách hàng thành công.")
            return redirect("customer-home")
        form.add_error(None, "Tài khoản này không thuộc khu vực Customer.")
    return render(
        request, "accounts/login.html", {"form": form, "login_area": "Customer"}
    )


@never_cache
@ensure_csrf_cookie
def register(request):
    if request.user.is_authenticated:
        return redirect("dashboard")
    form = CustomerRegistrationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        request.session.cycle_key()
        request.session["customer_user_id"] = user.pk
        messages.success(request, "Đăng ký tài khoản thành công.")
        return redirect("customer-home")
    return render(request, "accounts/register.html", {"form": form})


def dashboard(request):
    if request.user.is_authenticated and request.user.role == User.Role.ADMIN:
        return redirect("admin-home")
    if request.staff_user is not None:
        return redirect("staff-home")
    if request.customer_user is not None:
        return redirect("customer-home")
    return redirect("login")


@customer_required
def customer_home(request):
    return render(request, "accounts/customer_home.html")


def customer_logout(request):
    if request.method == "POST":
        request.session.pop("customer_user_id", None)
        return redirect("login")
    return render(
        request,
        "accounts/logout.html",
        {"logout_area": "Customer", "cancel_url": "/customer/"},
    )
