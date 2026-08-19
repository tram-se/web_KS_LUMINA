from django.db import models


class RoomType(models.Model):
    name = models.CharField("Tên loại phòng", max_length=120, unique=True)
    code = models.CharField("Mã loại", max_length=30, unique=True)
    description = models.TextField("Mô tả", blank=True)
    max_guests = models.PositiveSmallIntegerField("Số khách tối đa", default=2)
    area_sqm = models.PositiveSmallIntegerField("Diện tích (m²)", default=25)
    is_active = models.BooleanField("Đang kinh doanh", default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("name",)
        verbose_name = "Loại phòng"
        verbose_name_plural = "Loại phòng"

    def __str__(self):
        return f"{self.name} ({self.code})"


class Room(models.Model):
    class Status(models.TextChoices):
        AVAILABLE = "AVAILABLE", "Còn trống"
        BOOKED = "BOOKED", "Đã đặt"
        OCCUPIED = "OCCUPIED", "Đang sử dụng"
        MAINTENANCE = "MAINTENANCE", "Đang bảo trì"

    number = models.CharField("Số phòng", max_length=20, unique=True)
    room_type = models.ForeignKey(
        RoomType,
        on_delete=models.PROTECT,
        related_name="rooms",
        verbose_name="Loại phòng",
    )
    floor = models.PositiveSmallIntegerField("Tầng", default=1)
    status = models.CharField(
        "Tình trạng",
        max_length=20,
        choices=Status.choices,
        default=Status.AVAILABLE,
    )
    note = models.TextField("Ghi chú", blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("number",)
        verbose_name = "Phòng"
        verbose_name_plural = "Phòng"

    def __str__(self):
        return f"Phòng {self.number} - {self.room_type.name}"


class RoomPrice(models.Model):
    room_type = models.ForeignKey(
        RoomType,
        on_delete=models.CASCADE,
        related_name="prices",
        verbose_name="Loại phòng",
    )
    price = models.DecimalField("Giá/đêm", max_digits=12, decimal_places=0)
    valid_from = models.DateField("Áp dụng từ")
    valid_to = models.DateField("Áp dụng đến", null=True, blank=True)
    is_active = models.BooleanField("Đang áp dụng", default=True)
    note = models.CharField("Ghi chú", max_length=255, blank=True)

    class Meta:
        ordering = ("-valid_from",)
        verbose_name = "Giá phòng"
        verbose_name_plural = "Giá phòng"

    def __str__(self):
        return f"{self.room_type.name} - {self.price:,.0f}đ"


class Amenity(models.Model):
    name = models.CharField("Tên tiện nghi", max_length=120, unique=True)
    description = models.CharField("Mô tả", max_length=255, blank=True)
    is_active = models.BooleanField("Đang cung cấp", default=True)

    class Meta:
        ordering = ("name",)
        verbose_name = "Tiện nghi"
        verbose_name_plural = "Tiện nghi"

    def __str__(self):
        return self.name


class Service(models.Model):
    name = models.CharField("Tên dịch vụ", max_length=120, unique=True)
    description = models.TextField("Mô tả", blank=True)
    price = models.DecimalField("Giá niêm yết", max_digits=12, decimal_places=0)
    unit = models.CharField("Đơn vị tính", max_length=50, default="lần")
    is_active = models.BooleanField("Đang cung cấp", default=True)

    class Meta:
        ordering = ("name",)
        verbose_name = "Dịch vụ"
        verbose_name_plural = "Dịch vụ"

    def __str__(self):
        return self.name


class ActivityLog(models.Model):
    class Level(models.TextChoices):
        INFO = "INFO", "Thông tin"
        WARNING = "WARNING", "Cảnh báo"
        SUCCESS = "SUCCESS", "Thành công"

    action = models.CharField("Hoạt động", max_length=180)
    actor = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="activity_logs",
        verbose_name="Người thực hiện",
    )
    level = models.CharField(
        "Mức độ", max_length=20, choices=Level.choices, default=Level.INFO
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)
        verbose_name = "Nhật ký hoạt động"
        verbose_name_plural = "Nhật ký hoạt động"

    def __str__(self):
        return self.action
