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
        PENDING = "PENDING", "Chờ xử lý"
        CONFIRMED = "CONFIRMED", "Đã xác nhận"
        CANCELLED = "CANCELLED", "Đã hủy"

    customer = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name="bookings"
    )
    booking_code = models.CharField(max_length=20, unique=True)
    room_type = models.CharField(max_length=100)
    check_in = models.DateField()
    check_out = models.DateField()
    guest_count = models.PositiveSmallIntegerField(default=1)
    total_price = models.DecimalField(max_digits=12, decimal_places=0, default=0)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING
    )
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self):
        return self.booking_code


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
