from django import forms
from django.contrib import admin
from django.contrib import messages
from PIL import Image, UnidentifiedImageError

from .models import (
    ActivityLog,
    Amenity,
    Room,
    RoomImage,
    RoomPrice,
    RoomType,
    Service,
    compress_image,
)


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


class RoomTypeAdminForm(forms.ModelForm):
    gallery_images = MultipleImageField(
        label="Ảnh gallery",
        required=False,
        widget=MultipleFileInput(attrs={"multiple": True, "accept": "image/*"}),
    )

    class Meta:
        model = RoomType
        fields = "__all__"

    def clean_gallery_images(self):
        images = self.cleaned_data.get("gallery_images", [])
        for image in images:
            if image.size > 20 * 1024 * 1024:
                raise forms.ValidationError("Mỗi ảnh không được vượt quá 20MB.")
        return images

    class Media:
        js = ("admin/room_gallery_preview.js",)


@admin.register(RoomType)
class RoomTypeAdmin(admin.ModelAdmin):
    form = RoomTypeAdminForm
    actions = ("approve_selected_room_types",)
    list_display = ("name", "code", "listing_status", "max_guests", "is_active")
    list_filter = ("listing_status", "is_active")
    search_fields = ("name", "code")
    filter_horizontal = ("amenities",)

    def save_model(self, request, obj, form, change):
        if obj.image_url:
            obj.image_url = compress_image(obj.image_url)
        super().save_model(request, obj, form, change)
        for image in form.cleaned_data.get("gallery_images", []):
            RoomImage.objects.create(room_type=obj, image=image)

    @admin.action(description="Duyệt tất cả loại phòng đã chọn")
    def approve_selected_room_types(self, request, queryset):
        pending = queryset.filter(listing_status=RoomType.ListingStatus.PENDING)
        approved_count = pending.update(
            listing_status=RoomType.ListingStatus.PUBLISHED,
            is_active=True,
        )
        if approved_count:
            self.message_user(
                request,
                f"Đã duyệt {approved_count} loại phòng đã chọn.",
                messages.SUCCESS,
            )
        else:
            self.message_user(
                request,
                "Không có loại phòng đang chờ duyệt trong lựa chọn.",
                messages.WARNING,
            )


@admin.register(Room)
class RoomAdmin(admin.ModelAdmin):
    list_display = ("number", "room_type", "floor", "status", "updated_at")
    list_filter = ("status", "room_type")
    search_fields = ("number", "room_type__name")
    autocomplete_fields = ("room_type",)


@admin.register(RoomImage)
class RoomImageAdmin(admin.ModelAdmin):
    list_display = ("room_type", "image", "uploaded_at")
    list_filter = ("room_type",)
    autocomplete_fields = ("room_type",)


@admin.register(RoomPrice)
class RoomPriceAdmin(admin.ModelAdmin):
    list_display = ("room_type", "price", "unit", "valid_from", "valid_to", "is_active")
    list_filter = ("unit", "is_active", "room_type")
    autocomplete_fields = ("room_type",)


@admin.register(Amenity)
class AmenityAdmin(admin.ModelAdmin):
    list_display = ("name", "description", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name",)


@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    list_display = ("name", "price", "unit", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name",)


@admin.register(ActivityLog)
class ActivityLogAdmin(admin.ModelAdmin):
    list_display = ("action", "actor", "level", "created_at")
    list_filter = ("level", "created_at")
    search_fields = ("action", "actor__full_name")
    readonly_fields = ("created_at",)
