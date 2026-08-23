from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("store", "0016_pet_image")]

    operations = [
        migrations.AddField(
            model_name="product",
            name="is_archived",
            field=models.BooleanField(db_index=True, default=False, help_text="Hides the product from customers without deleting its history."),
        ),
    ]
