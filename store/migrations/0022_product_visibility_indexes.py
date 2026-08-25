from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("store", "0021_productimage_external_url"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="product",
            index=models.Index(
                fields=["is_archived", "is_available", "category"],
                name="store_prod_vis_cat_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="product",
            index=models.Index(
                fields=["is_archived", "is_available", "pet_type"],
                name="store_prod_vis_pet_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="product",
            index=models.Index(
                fields=["is_archived", "is_available", "brand"],
                name="store_prod_vis_brand_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="product",
            index=models.Index(
                fields=["category", "is_archived", "is_available", "is_featured"],
                name="store_prod_cat_sort_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="product",
            index=models.Index(
                fields=["is_archived", "is_available", "price"],
                name="store_prod_vis_price_idx",
            ),
        ),
    ]
