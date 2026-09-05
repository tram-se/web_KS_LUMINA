import uuid

from django.contrib.auth.models import AbstractUser, UserManager
from django.db import models


class LuminaUserManager(UserManager):
    def create_superuser(self, username, email=None, password=None, **extra_fields):
        extra_fields.setdefault("role", User.Role.ADMIN)
        extra_fields.setdefault("full_name", username)
        return super().create_superuser(username, email, password, **extra_fields)


class User(AbstractUser):
    class Role(models.TextChoices):
        CUSTOMER = "CUSTOMER", "Customer"
        STAFF = "STAFF", "Staff"
        ADMIN = "ADMIN", "Admin"

    full_name = models.CharField("full name", max_length=150)
    email = models.EmailField("email", unique=True)
    phone_number = models.CharField("phone number", max_length=20, blank=True)
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.CUSTOMER)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    objects = LuminaUserManager()

    def save(self, *args, **kwargs):
        self.is_staff = self.is_staff or self.role in {self.Role.STAFF, self.Role.ADMIN}
        self.is_superuser = self.is_superuser or self.role == self.Role.ADMIN
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.full_name} ({self.username})"


class Booking(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", "Chờ xác nhận"
        CONFIRMED = "CONFIRMED", "Đã xác nhận"
        CHECKED_IN = "CHECKED_IN", "Đã check-in"
        CHECKED_OUT = "CHECKED_OUT", "Đã check-out"
        CANCELLED = "CANCELLED", "Đã hủy"

    class PaymentStatus(models.TextChoices):
        UNPAID = "UNPAID", "Chưa thanh toán"
        PENDING = "PENDING", "Chờ xác nhận thanh toán"
        PAID = "PAID", "Đã thanh toán"
        REJECTED = "REJECTED", "Thanh toán bị từ chối"

    customer = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name="bookings"
    )
    guest_full_name = models.CharField("Họ và tên khách", max_length=150, blank=True)
    guest_phone = models.CharField("Số điện thoại khách", max_length=20, blank=True)
    guest_id_number = models.CharField("CCCD/CMND", max_length=20, blank=True)
    id_card_front_image = models.ImageField(
        "Ảnh CCCD mặt trước",
        upload_to="booking-id-cards/",
        blank=True,
        null=True,
    )
    id_card_back_image = models.ImageField(
        "Ảnh CCCD mặt sau",
        upload_to="booking-id-cards/",
        blank=True,
        null=True,
    )
    room = models.ForeignKey(
        "admin_panel.Room",
        on_delete=models.PROTECT,
        related_name="bookings",
        null=True,
        blank=True,
        verbose_name="Phòng",
    )
    booking_code = models.CharField(max_length=20, unique=True)
    room_type = models.CharField(max_length=100)
    check_in = models.DateField()
    check_in_time = models.TimeField(default="14:00")
    check_out = models.DateField()
    check_out_time = models.TimeField(default="12:00")
    guest_count = models.PositiveSmallIntegerField(default=1)
    total_price = models.DecimalField(max_digits=12, decimal_places=0, default=0)
    payment_status = models.CharField(
        "Trạng thái thanh toán",
        max_length=20,
        choices=PaymentStatus.choices,
        default=PaymentStatus.UNPAID,
    )
    payment_reference = models.CharField(
        "Mã giao dịch", max_length=100, blank=True
    )
    payment_proof = models.ImageField(
        "Ảnh biên lai thanh toán",
        upload_to="payment-proofs/",
        blank=True,
        null=True,
    )
    momo_order_id = models.CharField("MoMo order ID", max_length=100, blank=True)
    momo_request_id = models.CharField("MoMo request ID", max_length=100, blank=True)
    paid_at = models.DateTimeField("Thời điểm thanh toán", null=True, blank=True)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING
    )
    notes = models.TextField(blank=True)
    qr_token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self):
        return self.booking_code


class CheckInRequest(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", "Chờ staff xác nhận"
        APPROVED = "APPROVED", "Đã xác nhận check-in"
        REJECTED = "REJECTED", "Đã từ chối"

    booking = models.OneToOneField(
        Booking, on_delete=models.CASCADE, related_name="check_in_request"
    )
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING
    )
    requested_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    staff_note = models.TextField(blank=True)

    class Meta:
        ordering = ("-requested_at",)


class ConsultationRequest(models.Model):
    class Status(models.TextChoices):
        NEW = "NEW", "Mới"
        CONTACTED = "CONTACTED", "Đã liên hệ"
        CLOSED = "CLOSED", "Đã hoàn tất"

    full_name = models.CharField(max_length=150)
    phone_number = models.CharField(max_length=20)
    preferred_room = models.CharField(max_length=100, blank=True)
    message = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.NEW)
    staff_note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self):
        return f"{self.full_name} - {self.phone_number}"
