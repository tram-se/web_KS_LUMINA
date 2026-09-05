from datetime import date
import re

import cv2
import numpy as np
import zxingcpp
from django import forms
from django.contrib.auth import authenticate
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from PIL import Image, ImageOps, UnidentifiedImageError

from admin_panel.models import RoomType

from .models import User


class CustomerRegistrationForm(UserCreationForm):
    class Meta:
        model = User
        fields = ("full_name", "email", "phone_number")
        labels = {
            "full_name": "Họ và tên",
            "email": "Email",
            "phone_number": "Số điện thoại",
        }

    def clean_email(self):
        email = self.cleaned_data["email"].lower().strip()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("Email này đã được sử dụng.")
        return email

    def save(self, commit=True):
        user = super().save(commit=False)
        email = self.cleaned_data["email"]
        base_username = email.split("@", 1)[0][:140] or "customer"
        username = base_username
        suffix = 1
        while User.objects.filter(username=username).exists():
            suffix += 1
            username = f"{base_username}{suffix}"
        user.username = username
        user.role = User.Role.CUSTOMER
        if commit:
            user.save()
        return user


class CustomerProfileForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ("full_name", "email", "phone_number")
        labels = {
            "full_name": "Họ và tên",
            "email": "Email",
            "phone_number": "Số điện thoại",
        }


class CustomerLoginForm(AuthenticationForm):
    username = forms.EmailField(label="Email")

    def clean(self):
        cleaned_data = super(AuthenticationForm, self).clean()
        email = cleaned_data.get("username")
        password = cleaned_data.get("password")
        if email and password:
            account = User.objects.filter(email__iexact=email).first()
            self.user_cache = authenticate(
                self.request,
                username=account.username if account else email,
                password=password,
            )
            if self.user_cache is None:
                raise forms.ValidationError(
                    "Email hoặc mật khẩu không chính xác.",
                    code="invalid_login",
                )
            self.confirm_login_allowed(self.user_cache)
        return cleaned_data


class RoomSearchForm(forms.Form):
    check_in = forms.DateField(
        label="Ngày nhận phòng",
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    check_out = forms.DateField(
        label="Ngày trả phòng",
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    room_type = forms.ModelChoiceField(
        label="Loại phòng",
        required=False,
        queryset=RoomType.objects.filter(is_active=True),
        empty_label="Tất cả loại phòng",
    )
    guests = forms.IntegerField(label="Số khách", required=False, min_value=1)
    max_price = forms.DecimalField(
        label="Giá tối đa/đêm",
        required=False,
        min_value=0,
        max_digits=12,
        decimal_places=0,
    )

    def clean(self):
        cleaned_data = super().clean()
        check_in = cleaned_data.get("check_in")
        check_out = cleaned_data.get("check_out")
        if check_in and check_in < date.today():
            self.add_error("check_in", "Ngày nhận phòng không được ở quá khứ.")
        if check_in and check_out and check_out <= check_in:
            self.add_error("check_out", "Ngày trả phòng phải sau ngày nhận phòng.")
        return cleaned_data


class BookingRequestForm(forms.Form):
    guest_full_name = forms.CharField(label="Họ và tên", max_length=150)
    guest_phone = forms.CharField(label="Số điện thoại", max_length=20)
    guest_id_number = forms.CharField(label="Số CCCD / CMND", max_length=20)
    id_card_front_image = forms.FileField(
        label="Ảnh CCCD mặt trước",
        required=False,
        help_text="Chấp nhận mọi định dạng ảnh mà hệ thống đọc được, không giới hạn dung lượng.",
    )
    id_card_back_image = forms.FileField(
        label="Ảnh CCCD mặt sau",
        required=False,
        help_text="Tải ảnh mặt sau CCCD để lễ tân đối chiếu.",
    )
    check_in_time = forms.TimeField(
        label="Giờ nhận phòng", widget=forms.TimeInput(attrs={"type": "time"}), initial="14:00"
    )
    check_in = forms.DateField(
        label="Ngày nhận phòng",
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    check_out = forms.DateField(
        label="Ngày trả phòng",
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    check_out_time = forms.TimeField(
        label="Giờ trả phòng", widget=forms.TimeInput(attrs={"type": "time"}), initial="12:00"
    )
    guest_count = forms.IntegerField(label="Số khách", min_value=1, initial=1)
    notes = forms.CharField(
        label="Ghi chú cho khách sạn",
        required=False,
        widget=forms.Textarea(attrs={"rows": 4}),
    )

    def __init__(self, *args, customer=None, **kwargs):
        super().__init__(*args, **kwargs)
        if customer:
            self.fields["guest_full_name"].initial = customer.full_name
            self.fields["guest_phone"].initial = customer.phone_number

    def clean(self):
        cleaned_data = super().clean()
        check_in = cleaned_data.get("check_in")
        check_out = cleaned_data.get("check_out")
        if check_in and check_in < date.today():
            self.add_error("check_in", "Ngày nhận phòng không được ở quá khứ.")
        if check_in and check_out and check_out <= check_in:
            self.add_error("check_out", "Ngày trả phòng phải sau ngày nhận phòng.")
        if not cleaned_data.get("id_card_front_image"):
            self.add_error("id_card_front_image", "Vui lòng chọn ảnh CCCD mặt trước.")
        if not cleaned_data.get("id_card_back_image"):
            self.add_error("id_card_back_image", "Vui lòng chọn ảnh CCCD mặt sau.")
        for field_name in ("id_card_front_image", "id_card_back_image"):
            image = self.cleaned_data.get(field_name)
            if not image:
                continue
            try:
                with Image.open(image) as decoded_image:
                    decoded_image.verify()
            except (UnidentifiedImageError, OSError, ValueError):
                self.add_error(field_name, "Ảnh CCCD không hợp lệ.")
            image.seek(0)

        front_image = self.cleaned_data.get("id_card_front_image")
        id_number = re.sub(r"\D", "", cleaned_data.get("guest_id_number", ""))
        if front_image and id_number and not self.errors.get("id_card_front_image"):
            qr_data = ""
            try:
                front_image.seek(0)
                with Image.open(front_image) as uploaded_image:
                    corrected_image = ImageOps.exif_transpose(uploaded_image).convert("RGB")
                    decoded_image = cv2.cvtColor(
                        np.asarray(corrected_image), cv2.COLOR_RGB2BGR
                    )
                detector = cv2.QRCodeDetector()
                image_variants = [decoded_image]
                height, width = decoded_image.shape[:2]
                if max(height, width) < 2400:
                    image_variants.append(
                        cv2.resize(decoded_image, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
                    )
                for image_variant in image_variants:
                    gray_image = cv2.cvtColor(image_variant, cv2.COLOR_BGR2GRAY)
                    threshold_image = cv2.adaptiveThreshold(
                        gray_image,
                        255,
                        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                        cv2.THRESH_BINARY,
                        31,
                        5,
                    )
                    for candidate in (image_variant, gray_image, threshold_image):
                        try:
                            barcodes = zxingcpp.read_barcodes(candidate)
                        except Exception:
                            barcodes = []
                        if barcodes:
                            qr_data = barcodes[0].text
                        if qr_data:
                            break
                        qr_data, _, _ = detector.detectAndDecode(candidate)
                        if qr_data:
                            break
                    if qr_data:
                        break
            except (OSError, ValueError, cv2.error):
                qr_data = ""
            qr_numbers = re.findall(r"(?<!\d)\d{12}(?!\d)", qr_data or "")
            if not qr_numbers:
                self.add_error(
                    "id_card_front_image",
                    "Không tìm thấy mã QR CCCD hợp lệ trong ảnh mặt trước.",
                )
            elif qr_numbers[0] != id_number:
                self.add_error(
                    "id_card_front_image",
                    "Mã QR không khớp với số CCCD đã nhập.",
                )
            front_image.seek(0)
        return cleaned_data


class PaymentProofForm(forms.Form):
    payment_reference = forms.CharField(
        label="Mã giao dịch",
        max_length=100,
        required=False,
        help_text="Có thể bỏ trống nếu biên lai không hiển thị mã giao dịch.",
    )
    payment_proof = forms.FileField(
        label="Ảnh biên lai chuyển khoản",
        help_text="Tải ảnh chụp biên lai có ngày giờ, số tiền và mã giao dịch.",
    )

    def clean_payment_proof(self):
        proof = self.cleaned_data["payment_proof"]
        try:
            with Image.open(proof) as image:
                image.verify()
        except (UnidentifiedImageError, OSError, ValueError):
            raise forms.ValidationError("Biên lai phải là một file ảnh hợp lệ.")
        proof.seek(0)
        return proof


class PaymentReferenceForm(forms.Form):
    payment_reference = forms.CharField(
        label="Mã giao dịch ngân hàng",
        max_length=100,
        help_text="Nhập mã giao dịch sau khi chuyển khoản thành công.",
    )
