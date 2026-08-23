from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("store", "0019_coupon_order_coupon_code_order_discount_amount_and_more")]

    operations = [
        migrations.AddField(model_name="product", name="external_image_url", field=models.URLField(blank=True, max_length=1000)),
        migrations.AddField(model_name="product", name="source_url", field=models.URLField(blank=True, max_length=1000)),
        migrations.AddField(model_name="product", name="supplier_product_id", field=models.CharField(blank=True, db_index=True, max_length=80)),
        migrations.AddField(model_name="productvariant", name="external_image_url", field=models.URLField(blank=True, max_length=1000)),
        migrations.AddField(model_name="productvariant", name="supplier_variant_id", field=models.CharField(blank=True, db_index=True, max_length=80)),
    ]
