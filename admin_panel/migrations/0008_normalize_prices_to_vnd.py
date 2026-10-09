from django.db import migrations
from django.db.models import F


def convert_prices_to_vnd(apps, schema_editor):
    RoomPrice = apps.get_model("admin_panel", "RoomPrice")
    RoomPrice.objects.all().update(price=F("price") * 1000)


class Migration(migrations.Migration):
    dependencies = [
        ("admin_panel", "0007_alter_room_status"),
    ]

    operations = [
        migrations.RunPython(convert_prices_to_vnd, migrations.RunPython.noop),
    ]
