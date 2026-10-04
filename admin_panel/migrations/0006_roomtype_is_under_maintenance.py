from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("admin_panel", "0005_alter_roomimage_image"),
    ]

    operations = [
        migrations.AddField(
            model_name="roomtype",
            name="is_under_maintenance",
            field=models.BooleanField(
                default=False,
                help_text="Bật để tạm ngừng nhận đặt phòng cho toàn bộ hạng phòng này.",
                verbose_name="Đang sửa chữa",
            ),
        ),
    ]
