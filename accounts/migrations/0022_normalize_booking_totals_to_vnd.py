from django.db import migrations
from django.db.models import F


def convert_booking_totals_to_vnd(apps, schema_editor):
    Booking = apps.get_model("accounts", "Booking")
    Booking.objects.all().update(
        total_price=F("total_price") * 1000
    )


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0021_bookingroom_booking_room_quantity"),
    ]

    operations = [
        migrations.RunPython(convert_booking_totals_to_vnd, migrations.RunPython.noop),
    ]
