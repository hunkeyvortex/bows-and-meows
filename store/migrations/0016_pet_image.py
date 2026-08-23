from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("store", "0015_product_veterinary_fields")]

    operations = [
        migrations.AddField(
            model_name="pet",
            name="image",
            field=models.ImageField(blank=True, null=True, upload_to="pets/"),
        ),
    ]
