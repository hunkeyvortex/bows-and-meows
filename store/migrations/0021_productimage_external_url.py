from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("store", "0020_supplier_catalog_fields")]

    operations = [
        migrations.AlterField(
            model_name="productimage",
            name="image",
            field=models.ImageField(blank=True, null=True, upload_to="products/gallery/"),
        ),
        migrations.AddField(
            model_name="productimage",
            name="external_image_url",
            field=models.URLField(blank=True, max_length=1000),
        ),
    ]
