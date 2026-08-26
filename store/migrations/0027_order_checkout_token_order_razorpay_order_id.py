from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("store", "0026_alter_order_status"),
    ]

    operations = [
        migrations.AddField(
            model_name="order",
            name="checkout_token",
            field=models.UUIDField(
                blank=True,
                editable=False,
                help_text="Idempotency token preventing duplicate checkout submissions.",
                null=True,
                unique=True,
            ),
        ),
        migrations.AddField(
            model_name="order",
            name="razorpay_order_id",
            field=models.CharField(
                blank=True,
                editable=False,
                help_text="Server-created Razorpay order associated with this store order.",
                max_length=100,
                null=True,
                unique=True,
            ),
        ),
    ]
