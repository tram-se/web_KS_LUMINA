from django import forms
from accounts.models import Booking, ConsultationRequest, User


class BookingStatusForm(forms.ModelForm):
    class Meta:
        model = Booking
        fields = ("status", "notes")
        labels = {"status": "Trạng thái đơn", "notes": "Ghi chú xử lý"}
        widgets = {"notes": forms.Textarea(attrs={"rows": 4})}


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
