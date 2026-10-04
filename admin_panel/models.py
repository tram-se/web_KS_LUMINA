from io import BytesIO

from django.core.files.base import ContentFile
from django.db import models
from PIL import Image


def compress_image(uploaded_file, max_size=2 * 1024 * 1024):
    # Nén ảnh tải lên trước khi lưu để giảm dung lượng CSDL/media.
    image = Image.open(uploaded_file)
    image = image.convert("RGB")
    image.thumbnail((2400, 2400), Image.Resampling.LANCZOS)
    quality = 85
    output = BytesIO()
    image.save(output, format="JPEG", quality=quality, optimize=True)
    while output.tell() > max_size and quality > 35:
        quality -= 10
        output = BytesIO()
        image.save(output, format="JPEG", quality=quality, optimize=True)
    return ContentFile(
        output.getvalue(), name=f"{uploaded_file.name.rsplit('.', 1)[0]}.jpg"
    )


class RoomType(models.Model):
    # Lưu thông tin chung của một hạng phòng, ví dụ Deluxe hoặc Couple.
    class ListingStatus(models.TextChoices):
        PENDING = "PENDING", "Chờ duyệt"
        PUBLISHED = "PUBLISHED", "Đã duyệt"
        REJECTED = "REJECTED", "Từ chối"

    name = models.CharField("Tên loại phòng", max_length=120, unique=True)
    code = models.CharField("Mã loại", max_length=30, unique=True)
    description = models.TextField("Mô tả", blank=True)
    max_guests = models.PositiveSmallIntegerField("Số khách tối đa", default=2)
    area_sqm = models.PositiveSmallIntegerField("Diện tích (m²)", default=25)
    image_url = models.ImageField("Ảnh phòng", upload_to="room-listings/", blank=True)
    amenities = models.ManyToManyField(
        "Amenity",
        blank=True,
        related_name="room_types",
        verbose_name="Tiện nghi",
    )
    is_active = models.BooleanField("Đang kinh doanh", default=True)
    is_under_maintenance = models.BooleanField(
        "Đang sửa chữa",
        default=False,
        help_text="Bật để tạm ngừng nhận đặt phòng cho toàn bộ hạng phòng này.",
    )
    listing_status = models.CharField(
        "Trạng thái đăng bán",
        max_length=20,
        choices=ListingStatus.choices,
        default=ListingStatus.PUBLISHED,
    )
    created_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="room_listings",
        verbose_name="Nhân viên đăng",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("name",)
        verbose_name = "Loại phòng"
        verbose_name_plural = "Loại phòng"

    def __str__(self):
        return f"{self.name} ({self.code})"

    @property
    def total_quantity(self):
        return self.rooms.count()


class RoomImage(models.Model):
    # Lưu nhiều ảnh gallery thuộc cùng một hạng phòng.
    room_type = models.ForeignKey(
        RoomType,
        on_delete=models.CASCADE,
        related_name="images",
        verbose_name="Loại phòng",
    )
    image = models.ImageField("Hình ảnh", upload_to="room-listings/")
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("uploaded_at",)
        verbose_name = "Ảnh phòng"
        verbose_name_plural = "Ảnh phòng"

    def save(self, *args, **kwargs):
        # Chuẩn hóa và nén ảnh gallery trước khi ghi vào storage.
        if self.image:
            self.image = compress_image(self.image)
        super().save(*args, **kwargs)


class Room(models.Model):
    # Lưu từng phòng vật lý có số phòng, tầng và trạng thái vận hành.
    class Status(models.TextChoices):
        AVAILABLE = "AVAILABLE", "Còn trống"
        DEPOSIT = "DEPOSIT", "Đang đặt cọc"
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
    # Lưu lịch sử giá theo thời gian để tìm đúng giá tại ngày nhận phòng.
    class Unit(models.TextChoices):
        NIGHT = "NIGHT", "Theo đêm"
        HOUR = "HOUR", "Theo giờ"

    room_type = models.ForeignKey(
        RoomType,
        on_delete=models.CASCADE,
        related_name="prices",
        verbose_name="Loại phòng",
    )
    price = models.DecimalField("Giá/đêm", max_digits=12, decimal_places=0)
    unit = models.CharField(
        "Đơn vị tính", max_length=10, choices=Unit.choices, default=Unit.NIGHT
    )
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
    # Danh mục tiện nghi có thể gắn cho nhiều hạng phòng.
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
    # Danh mục dịch vụ phụ trợ mà khách sạn cung cấp.
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
    # Nhật ký hành động của Admin/Staff để truy vết thao tác quản trị.
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
