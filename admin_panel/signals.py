from django.db.models.signals import post_save
from django.dispatch import receiver

from accounts.models import Booking, User

from .models import ActivityLog, Amenity, Room, RoomPrice, RoomType, Service


@receiver(post_save, sender=User)
def log_user_change(sender, instance, created, **kwargs):
    action = "Tạo tài khoản" if created else "Cập nhật tài khoản"
    ActivityLog.objects.create(action=f"{action}: {instance.full_name}")


@receiver(post_save, sender=Booking)
def log_booking_change(sender, instance, created, **kwargs):
    action = "Tạo đơn đặt phòng" if created else "Cập nhật đơn đặt phòng"
    ActivityLog.objects.create(action=f"{action}: {instance.booking_code}")


@receiver(post_save, sender=Room)
def log_room_change(sender, instance, created, **kwargs):
    action = "Thêm phòng" if created else "Cập nhật phòng"
    ActivityLog.objects.create(action=f"{action}: {instance.number}")


@receiver(post_save, sender=RoomType)
def log_room_type_change(sender, instance, created, **kwargs):
    action = "Tạo loại phòng" if created else "Cập nhật loại phòng"
    ActivityLog.objects.create(action=f"{action}: {instance.name}")


@receiver(post_save, sender=RoomPrice)
def log_room_price_change(sender, instance, created, **kwargs):
    action = "Tạo giá phòng" if created else "Cập nhật giá phòng"
    ActivityLog.objects.create(action=f"{action}: {instance.room_type.name}")


@receiver(post_save, sender=Amenity)
def log_amenity_change(sender, instance, created, **kwargs):
    action = "Tạo tiện nghi" if created else "Cập nhật tiện nghi"
    ActivityLog.objects.create(action=f"{action}: {instance.name}")


@receiver(post_save, sender=Service)
def log_service_change(sender, instance, created, **kwargs):
    action = "Tạo dịch vụ" if created else "Cập nhật dịch vụ"
    ActivityLog.objects.create(action=f"{action}: {instance.name}")
