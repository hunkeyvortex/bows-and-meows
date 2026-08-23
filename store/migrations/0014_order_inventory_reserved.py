from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("store", "0013_productimage"),
    ]

    operations = [
        migrations.AddField(
            model_name="order",
            name="inventory_reserved",
            field=models.BooleanField(
                default=False,
                help_text="Whether this order's quantities are currently deducted from stock.",
            ),
        ),
    ]
