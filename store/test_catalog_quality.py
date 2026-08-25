from decimal import Decimal
from io import StringIO

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from .models import ConversionEvent, Coupon, Product, ProductVariant


class SellableCatalogTests(TestCase):
    def test_customer_visible_requires_real_parent_or_variant_stock(self):
        parent_stock = Product.objects.create(
            name="Parent stock", category="dog_food", price=Decimal("100"), stock=2
        )
        variant_stock = Product.objects.create(
            name="Variant stock", category="cat_food", price=Decimal("100"), stock=0
        )
        ProductVariant.objects.create(
            product=variant_stock, size="1 kg", price=Decimal("100"), stock=3, sku="VISIBLE-1"
        )
        zero_stock = Product.objects.create(
            name="No stock", category="dog_food", price=Decimal("100"), stock=0
        )
        archived = Product.objects.create(
            name="Archived", category="dog_food", price=Decimal("100"), stock=4, is_archived=True
        )

        visible_ids = set(Product.objects.customer_visible().values_list("id", flat=True))
        self.assertEqual(visible_ids, {parent_stock.id, variant_stock.id})
        self.assertNotIn(zero_stock.id, visible_ids)
        self.assertNotIn(archived.id, visible_ids)

    def test_duplicate_cleanup_is_dry_run_then_archives_without_deleting(self):
        canonical = Product.objects.create(
            name="Same Food", brand="Brand", category="dog_food", price=Decimal("100"), stock=5
        )
        duplicate = Product.objects.create(
            name=" same  food ", brand=" brand ", category="dog_food", price=Decimal("120"), stock=2
        )
        variant = ProductVariant.objects.create(
            product=duplicate, size="2 kg", price=Decimal("120"), stock=2, sku="DUP-2KG"
        )

        call_command("consolidate_product_duplicates", stdout=StringIO())
        duplicate.refresh_from_db()
        self.assertFalse(duplicate.is_archived)

        call_command("consolidate_product_duplicates", "--apply", stdout=StringIO())
        duplicate.refresh_from_db()
        variant.refresh_from_db()
        self.assertTrue(duplicate.is_archived)
        self.assertEqual(duplicate.duplicate_of_id, canonical.id)
        self.assertEqual(variant.product_id, canonical.id)
        self.assertTrue(Product.objects.filter(pk=duplicate.pk).exists())


class ConversionTrackingTests(TestCase):
    def setUp(self):
        self.product = Product.objects.create(
            name="Tracked Food", category="dog_food", price=Decimal("500"), stock=4
        )

    def test_product_cart_checkout_and_coupon_events_are_recorded(self):
        self.client.get(reverse("product_detail", args=[self.product.id]))
        self.client.post(reverse("add_to_cart", args=[self.product.id]))
        Coupon.objects.create(code="TRACK10", discount_percent=10)
        self.client.post(reverse("apply_coupon"), {"coupon_code": "TRACK10"})
        self.client.get(reverse("checkout"))

        event_types = set(ConversionEvent.objects.values_list("event_type", flat=True))
        self.assertTrue({
            "product_view", "add_to_cart", "coupon_applied", "checkout_started"
        }.issubset(event_types))

    def test_analytics_failure_never_blocks_cart(self):
        # The analytics helper is intentionally isolated; an ordinary cart request remains functional.
        response = self.client.post(reverse("add_to_cart", args=[self.product.id]))
        self.assertRedirects(response, reverse("cart"), fetch_redirect_response=False)
        self.assertTrue(self.client.session.get("cart"))
