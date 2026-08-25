from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("store", "0022_product_visibility_indexes"),
    ]

    operations = [
        migrations.AddField(
            model_name="product",
            name="duplicate_of",
            field=models.ForeignKey(
                blank=True,
                help_text="Canonical product retained when this duplicate is archived.",
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="archived_duplicates",
                to="store.product",
            ),
        ),
    ]
