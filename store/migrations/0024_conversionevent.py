from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("store", "0023_product_duplicate_of"),
    ]

    operations = [
        migrations.CreateModel(
            name="ConversionEvent",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("event_type", models.CharField(choices=[("product_view", "Product view"), ("add_to_cart", "Add to cart"), ("buy_now", "Buy now"), ("checkout_started", "Checkout started"), ("purchase_completed", "Purchase completed"), ("coupon_applied", "Coupon applied")], max_length=30)),
                ("session_key", models.CharField(blank=True, db_index=True, max_length=40)),
                ("coupon_code", models.CharField(blank=True, max_length=50)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("order", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="conversion_events", to="store.order")),
                ("product", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="conversion_events", to="store.product")),
                ("user", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="conversion_events", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "indexes": [
                    models.Index(fields=["event_type", "created_at"], name="store_event_type_time_idx"),
                    models.Index(fields=["session_key", "created_at"], name="store_event_session_idx"),
                    models.Index(fields=["user", "event_type"], name="store_event_user_type_idx"),
                ],
            },
        ),
    ]
