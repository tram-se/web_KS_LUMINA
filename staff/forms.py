from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.db.models import Q
from PIL import Image, UnidentifiedImageError

from accounts.models import Booking, ConsultationRequest, User
from admin_panel.models import Amenity, Room, RoomType


class StaffRegistrationForm(UserCreationForm):
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
        base_username = self.cleaned_data["email"].split("@", 1)[0][:140] or "staff"
        username = base_username
        suffix = 1
        while User.objects.filter(username=username).exists():
            suffix += 1
            username = f"{base_username}{suffix}"
        user.username = username
        user.role = User.Role.STAFF
        if commit:
            user.save()
        return user


class BookingStatusForm(forms.ModelForm):
    room = forms.ModelChoiceField(
        label="Số phòng cụ thể", queryset=Room.objects.all(), required=False
    )

    class Meta:
        model = Booking
        fields = ("status", "room", "notes")
        labels = {
            "status": "Trạng thái đơn",
            "room": "Số phòng cụ thể",
            "notes": "Ghi chú xử lý",
        }
        widgets = {"notes": forms.Textarea(attrs={"rows": 4})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        booking = self.instance

        room_queryset = Room.objects.filter(
            room_type__name=booking.room_type,
            status__in=[
                Room.Status.AVAILABLE,
                Room.Status.DEPOSIT,
                Room.Status.BOOKED,
            ],
        )

        # Luôn giữ phòng đã được tự động gán cho booking
        if booking.room:
            room_queryset = room_queryset | Room.objects.filter(
                pk=booking.room.pk
            )

        if booking.check_in and booking.check_out:
            conflicting_booking = Q(
                bookings__status__in=(
                    Booking.Status.PENDING,
                    Booking.Status.CONFIRMED,
                ),
                bookings__check_in__lt=booking.check_out,
                bookings__check_out__gt=booking.check_in,
            ) | Q(
                booking_assignments__booking__status__in=(
                    Booking.Status.PENDING,
                    Booking.Status.CONFIRMED,
                ),
                booking_assignments__booking__check_in__lt=booking.check_out,
                booking_assignments__booking__check_out__gt=booking.check_in,
            )
            conflicting_booking &= ~Q(bookings__pk=booking.pk)
            conflicting_booking &= ~Q(booking_assignments__booking__pk=booking.pk)

            room_queryset = room_queryset.exclude(conflicting_booking)

        self.fields["room"].queryset = room_queryset.distinct()
    def clean(self):
        cleaned_data = super().clean()
        
        return cleaned_data


class CustomerUpdateForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ("full_name", "email", "phone_number", "is_active")
        labels = {
            "full_name": "Họ và tên",
            "email": "Email",
            "phone_number": "Số điện thoại",
            "is_active": "Tài khoản đang hoạt động",
        }


class ConsultationStatusForm(forms.ModelForm):
    class Meta:
        model = ConsultationRequest
        fields = ("status", "staff_note")
        labels = {"status": "Trạng thái tư vấn", "staff_note": "Ghi chú tư vấn"}
        widgets = {"staff_note": forms.Textarea(attrs={"rows": 4})}


class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultipleImageField(forms.FileField):
    def clean(self, data, initial=None):
        if not data:
            return []
        if not isinstance(data, (list, tuple)):
            data = [data]
        cleaned = []
        for image in data:
            image = super().clean(image, initial)
            try:
                image.seek(0)
                with Image.open(image) as opened:
                    opened.verify()
                image.seek(0)
            except (UnidentifiedImageError, OSError):
                raise forms.ValidationError("Tệp được chọn không phải là ảnh hợp lệ.")
            cleaned.append(image)
        return cleaned


class RoomListingForm(forms.ModelForm):
    price = forms.DecimalField(
        label="Giá phòng", min_value=0, max_digits=12, decimal_places=0
    )
    price_unit = forms.ChoiceField(
        label="Đơn vị giá",
        choices=(("NIGHT", "Theo đêm"), ("HOUR", "Theo giờ")),
    )
    quantity = forms.IntegerField(label="Số lượng phòng", min_value=1, max_value=100)
    room_prefix = forms.CharField(
        label="Tiền tố số phòng", max_length=12, initial="LUM"
    )
    floor = forms.IntegerField(label="Tầng", min_value=1, initial=1)
    images = MultipleImageField(
        label="Hình ảnh phòng",
        required=False,
        widget=MultipleFileInput(attrs={"multiple": True, "accept": "image/*"}),
    )

    class Meta:
        model = RoomType
        fields = ("name", "code", "description", "max_guests", "area_sqm", "amenities")
        labels = {
            "name": "Hạng phòng",
            "code": "Mã loại phòng",
            "description": "Mô tả chi tiết",
            "max_guests": "Số khách tối đa",
            "area_sqm": "Diện tích (m²)",
            "amenities": "Tiện ích",
        }
        widgets = {"description": forms.Textarea(attrs={"rows": 5})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["amenities"].queryset = Amenity.objects.filter(is_active=True)

    def clean_images(self):
        images = self.cleaned_data.get("images", [])
        for image in images:
            if image.size > 20 * 1024 * 1024:
                raise forms.ValidationError("Mỗi hình ảnh không được vượt quá 20MB.")
        return images

    def clean_room_prefix(self):
        prefix = self.cleaned_data["room_prefix"].strip().upper()
        quantity = self.cleaned_data.get("quantity", 0)
        from admin_panel.models import Room

        numbers = [f"{prefix}-{number:02d}" for number in range(1, quantity + 1)]
        if Room.objects.filter(number__in=numbers).exists():
            raise forms.ValidationError(
                "Tiền tố này đã được dùng cho số phòng hiện có."
            )
        return prefix


class RoomListingEditForm(RoomListingForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        room_type = self.instance
        rooms = room_type.rooms.order_by("number")
        self.fields["quantity"].initial = rooms.count()
        self.fields["floor"].initial = rooms.first().floor if rooms.exists() else 1
        first_number = rooms.first().number if rooms.exists() else "LUM-01"
        self.fields["room_prefix"].initial = first_number.rsplit("-", 1)[0]
        price = room_type.prices.filter(is_active=True).first()
        if price:
            self.fields["price"].initial = price.price
            self.fields["price_unit"].initial = price.unit

    def clean_room_prefix(self):
        prefix = self.cleaned_data["room_prefix"].strip().upper()
        quantity = self.cleaned_data.get("quantity", 0)
        from admin_panel.models import Room

        numbers = [f"{prefix}-{number:02d}" for number in range(1, quantity + 1)]
        existing = Room.objects.filter(number__in=numbers).exclude(
            room_type=self.instance
        )
        if existing.exists():
            raise forms.ValidationError("Tiền tố này đã được dùng cho số phòng khác.")
        return prefix
