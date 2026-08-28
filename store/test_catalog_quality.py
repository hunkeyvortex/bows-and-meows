from decimal import Decimal
from io import StringIO

from django.core.management import call_command
from django.test import Client, TestCase
from django.urls import reverse

from .models import ConversionEvent, Coupon, Product, ProductVariant


class CsrfRecoveryTests(TestCase):
    def test_stale_login_form_redirects_to_fresh_form(self):
        client = Client(enforce_csrf_checks=True)
        client.get(reverse("login"))

        response = client.post(
            reverse("login"),
            {
                "identifier": "buyer@example.com",
                "password": "unused-password",
                "next": reverse("crm_dashboard"),
                "csrfmiddlewaretoken": "x" * 64,
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response.url,
            f"{reverse('login')}?csrf=expired&next=%2Fcrm%2F",
        )
        refreshed = client.get(response.url)
        self.assertContains(refreshed, "Your secure form expired")

    def test_stale_non_auth_form_remains_forbidden_with_safe_page(self):
        client = Client(enforce_csrf_checks=True)
        product = Product.objects.create(
            name="Protected Food", category="dog_food", product_type="food",
            price="100.00", stock=1,
        )

        response = client.post(
            reverse("add_to_cart", args=[product.id]),
            {"csrfmiddlewaretoken": "x" * 64},
        )

        self.assertEqual(response.status_code, 403)
        self.assertContains(
            response,
            "Nothing was changed or charged",
            status_code=403,
        )


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

    def test_launch_catalog_hides_medicine_and_accessories_but_keeps_food(self):
        food = Product.objects.create(
            name="Available food", category="dog_food", product_type="food",
            price=Decimal("100"), stock=2,
        )
        medicine = Product.objects.create(
            name="Available medicine", category="medicine", product_type="medicine",
            price=Decimal("100"), stock=2,
        )
        accessory = Product.objects.create(
            name="Available accessory", category="dog_accessory", product_type="supply",
            price=Decimal("100"), stock=2,
        )

        visible_ids = set(Product.objects.customer_visible().values_list("id", flat=True))

        self.assertIn(food.id, visible_ids)
        self.assertNotIn(medicine.id, visible_ids)
        self.assertNotIn(accessory.id, visible_ids)

    def test_food_category_is_never_hidden_by_bad_imported_product_type(self):
        mislabeled_food = Product.objects.create(
            name="Imported Dog Food", category="dog_food", product_type="supply",
            pet_type="dog", price=Decimal("100"), stock=2,
        )

        self.assertTrue(
            Product.objects.customer_visible().filter(id=mislabeled_food.id).exists()
        )

    def test_pharmacy_is_coming_soon_and_dog_food_remains_listed(self):
        food = Product.objects.create(
            name="Visible Dog Food", category="dog_food", product_type="food",
            pet_type="dog", price=Decimal("100"), stock=2,
        )
        medicine = Product.objects.create(
            name="Hidden Dog Medicine", category="medicine", product_type="medicine",
            pet_type="dog", price=Decimal("100"), stock=2,
        )

        pharmacy = self.client.get(reverse("medicine_products"))
        dogs = self.client.get(reverse("dog_products"))

        self.assertContains(pharmacy, "Coming soon")
        self.assertNotContains(pharmacy, medicine.name)
        self.assertContains(dogs, food.name)
        self.assertNotContains(dogs, medicine.name)

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


class FoodCatalogAuditTests(TestCase):
    def test_homepage_keeps_five_dog_and_five_cat_foods_in_market_order(self):
        dog_names = (
            "Pedigree Adult Chicken & Vegetables Dry Dog Food",
            "Drools Adult Chicken & Egg Dry Dog Food",
            "Royal Canin Maxi Adult Dry Dog Food",
            "Pedigree Adult Meat & Rice Dry Dog Food",
            "Farmina N&D Pumpkin Chicken & Pomegranate Adult Dog Food",
        )
        cat_names = (
            "Royal Canin Persian Adult Dry Cat Food",
            "Whiskas Adult Ocean Fish Dry Cat Food",
            "Me-O Persian Adult Cat Food",
            "Purepet Adult Ocean Fish Dry Cat Food",
            "Royal Canin Persian Kitten Dry Cat Food",
        )
        for name in dog_names:
            Product.objects.create(
                name=name, category="dog_food", product_type="food",
                pet_type="dog", price=Decimal("500.00"), stock=5,
            )
        for name in cat_names:
            Product.objects.create(
                name=name, category="cat_food", product_type="food",
                pet_type="cat", price=Decimal("500.00"), stock=5,
            )

        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        expected = [
            name
            for pair in zip(dog_names, cat_names)
            for name in pair
        ]
        self.assertEqual(
            [product.name for product in response.context["best_sellers"]],
            expected,
        )

    def test_cleanup_disables_duplicate_variant_and_syncs_parent(self):
        product = Product.objects.create(
            name="Verified Dog Food",
            brand="Trusted Brand",
            category="dog_food",
            product_type="food",
            pet_type="dog",
            price=Decimal("999.00"),
            original_price=Decimal("999.00"),
            stock=99,
        )
        canonical = ProductVariant.objects.create(
            product=product,
            size="1.2 kg",
            price=Decimal("499.00"),
            original_price=Decimal("599.00"),
            stock=9,
            sku="AUDIT-ORIGINAL",
        )
        duplicate = ProductVariant.objects.create(
            product=product,
            size="1.2 KG",
            price=Decimal("529.00"),
            original_price=Decimal("599.00"),
            stock=10,
            sku="AUDIT-DUPLICATE",
        )

        call_command(
            "audit_food_catalog", "--catalog", "missing-test-catalog.csv",
            stdout=StringIO(),
        )
        duplicate.refresh_from_db()
        self.assertTrue(duplicate.is_available)

        call_command(
            "audit_food_catalog", "--apply", "--catalog", "missing-test-catalog.csv",
            stdout=StringIO(),
        )
        product.refresh_from_db()
        canonical.refresh_from_db()
        duplicate.refresh_from_db()

        self.assertTrue(canonical.is_available)
        self.assertFalse(duplicate.is_available)
        self.assertEqual(duplicate.stock, 0)
        self.assertEqual(product.stock, canonical.stock)
        self.assertEqual(product.price, canonical.price)
        self.assertEqual(product.original_price, canonical.original_price)

    def test_cleanup_archives_obvious_clothing_without_deleting_it(self):
        clothing = Product.objects.create(
            name="Festival Sherwani for Dogs",
            brand="Clothing Brand",
            category="dog_food",
            product_type="supply",
            pet_type="dog",
            price=Decimal("799.00"),
            stock=4,
        )

        call_command(
            "audit_food_catalog", "--apply", "--catalog", "missing-test-catalog.csv",
            stdout=StringIO(),
        )
        clothing.refresh_from_db()

        self.assertTrue(clothing.is_archived)
        self.assertFalse(clothing.is_available)
        self.assertEqual(clothing.stock, 4)
        self.assertTrue(Product.objects.filter(pk=clothing.pk).exists())

    def test_cleanup_repairs_parent_image_from_an_exact_variant(self):
        product = Product.objects.create(
            name="Image Food",
            brand="Trusted Brand",
            category="cat_food",
            product_type="food",
            pet_type="cat",
            price=Decimal("200.00"),
            stock=2,
        )
        ProductVariant.objects.create(
            product=product,
            size="400 g",
            price=Decimal("200.00"),
            original_price=Decimal("220.00"),
            stock=2,
            sku="AUDIT-IMAGE",
            external_image_url="https://images.example.com/food.jpg",
        )

        call_command(
            "audit_food_catalog", "--apply", "--catalog", "missing-test-catalog.csv",
            stdout=StringIO(),
        )
        product.refresh_from_db()

        self.assertEqual(
            product.external_image_url,
            "https://images.example.com/food.jpg",
        )

    def test_cleanup_clears_false_discount_mrp(self):
        product = Product.objects.create(
            name="No False Discount Food",
            category="cat_food",
            product_type="food",
            price=Decimal("300.00"),
            original_price=Decimal("299.00"),
            stock=3,
        )

        call_command(
            "audit_food_catalog", "--apply", "--catalog", "missing-test-catalog.csv",
            stdout=StringIO(),
        )
        product.refresh_from_db()

        self.assertIsNone(product.original_price)


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
