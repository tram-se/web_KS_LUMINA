from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0020_chatbotfaq"),
    ]

    operations = [
        migrations.AddField(
            model_name="booking",
            name="room_quantity",
            field=models.PositiveSmallIntegerField(default=1, verbose_name="Số lượng phòng"),
        ),
        migrations.CreateModel(
            name="BookingRoom",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("booking", models.ForeignKey(on_delete=models.deletion.CASCADE, related_name="room_assignments", to="accounts.booking")),
                ("room", models.ForeignKey(on_delete=models.deletion.PROTECT, related_name="booking_assignments", to="admin_panel.room")),
            ],
        ),
        migrations.AddConstraint(
            model_name="bookingroom",
            constraint=models.UniqueConstraint(fields=("booking", "room"), name="unique_booking_room"),
        ),
    ]