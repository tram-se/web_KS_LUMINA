from django.contrib.auth.forms import UserCreationForm

from .models import User


class CustomerRegistrationForm(UserCreationForm):
    class Meta:
        model = User
        fields = ("username", "full_name", "email", "phone_number")
        labels = {
            "username": "Tên đăng nhập",
            "full_name": "Họ và tên",
            "email": "Email",
            "phone_number": "Số điện thoại",
        }

    def save(self, commit=True):
        user = super().save(commit=False)
        user.role = User.Role.CUSTOMER
        if commit:
            user.save()
        return user
