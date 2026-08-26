from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .models import (BundleItem, Coupon, DeliveryZone, OfferCampaign, Order, OrderItem,
                     Prescription, Product, ProductBundle, ProductVariant)
from .services.commerce import bundle_snapshot, frequently_bought, recently_viewed, remember_recently_viewed


def product(name="Dog Food", **overrides):
    values = {"name": name, "category": "dog_food", "pet_type": "dog", "price": Decimal("100.00"),
              "original_price": Decimal("120.00"), "stock": 10, "is_available": True}
    values.update(overrides)
    return Product.objects.create(**values)


class DeliveryZoneTests(TestCase):
    def test_valid_zone_and_cod_status(self):
        DeliveryZone.objects.create(pincode="400001", city="Mumbai", state="Maharashtra", cod_available=False)
        response = self.client.post(reverse("delivery_status"), {"pincode": "400001"})
        self.assertTrue(response.json()["available"])
        self.assertFalse(response.json()["cod_available"])
        self.assertEqual(self.client.session["delivery_pincode"], "400001")

    def test_malformed_and_inactive_zones_are_unavailable(self):
        DeliveryZone.objects.create(pincode="400002", city="Mumbai", state="Maharashtra", is_active=False)
        self.assertEqual(self.client.post(reverse("delivery_status"), {"pincode": "abc"}).status_code, 400)
        self.assertFalse(self.client.post(reverse("delivery_status"), {"pincode": "400002"}).json()["available"])


class CheckoutLaunchSafetyTests(TestCase):
    def setUp(self):
        self.item = product("Checkout Food", price=Decimal("500.00"), stock=3)
        self.zone = DeliveryZone.objects.create(
            pincode="400001", city="Mumbai", state="Maharashtra", cod_available=True
        )

    def seed_checkout(self, *, token=None, coupon=None):
        session = self.client.session
        session["cart"] = {
            f"p{self.item.id}": {
                "product_id": self.item.id,
                "variant_id": None,
                "quantity": 1,
            }
        }
        if token:
            session["checkout_token"] = token
        if coupon:
            session["coupon_code"] = coupon.code
        session["guest_checkout_confirmed"] = True
        session.save()
        self.client.get(reverse("checkout"))
        return str(self.client.session["checkout_token"])

    def checkout_data(self, token, **overrides):
        data = {
            "checkout_token": token,
            "customer_name": "Pet Parent",
            "email": "parent@example.com",
            "phone": "9876543210",
            "address": "1 Pet Street, Mumbai",
            "pincode": self.zone.pincode,
            "payment_method": "cod",
        }
        data.update(overrides)
        return data

    @patch("store.views.notify_order_confirmed")
    def test_cod_checkout_is_idempotent_and_coupon_counts_once(self, notify):
        coupon = Coupon.objects.create(code="LAUNCH10", discount_percent=10, usage_limit=5)
        token = self.seed_checkout(coupon=coupon)

        first = self.client.post(reverse("checkout"), self.checkout_data(token))
        self.assertEqual(first.status_code, 302)
        self.assertEqual(Order.objects.count(), 1)
        order = Order.objects.get()
        self.assertEqual(order.total_amount, Decimal("450.00"))
        self.assertEqual(order.checkout_token.hex, token.replace("-", ""))

        self.seed_checkout(token=token, coupon=coupon)
        second = self.client.post(reverse("checkout"), self.checkout_data(token))
        self.assertRedirects(second, reverse("order_success", args=[order.id]), fetch_redirect_response=False)
        self.assertEqual(Order.objects.count(), 1)
        coupon.refresh_from_db()
        self.item.refresh_from_db()
        self.assertEqual(coupon.times_used, 1)
        self.assertEqual(self.item.stock, 2)
        notify.assert_called_once()

    def test_checkout_rejects_unsupported_pincode_and_payment_method(self):
        token = self.seed_checkout()
        response = self.client.post(
            reverse("checkout"),
            self.checkout_data(token, pincode="999999"),
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(Order.objects.exists())

        response = self.client.post(
            reverse("checkout"),
            self.checkout_data(token, payment_method="free"),
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(Order.objects.exists())

    def test_checkout_enforces_zone_cod_policy(self):
        self.zone.cod_available = False
        self.zone.save(update_fields=["cod_available"])
        token = self.seed_checkout()
        response = self.client.post(reverse("checkout"), self.checkout_data(token))
        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "Cash on Delivery is not available", status_code=400)
        self.assertFalse(Order.objects.exists())


LOCAL_STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}


@override_settings(STORAGES=LOCAL_STORAGES)
class QuickViewAndRecentTests(TestCase):
    def test_quick_view_shows_available_variant(self):
        item = product()
        ProductVariant.objects.create(product=item, size="2 KG", price=90, original_price=110, stock=3)
        response = self.client.get(reverse("quick_view", args=[item.id]))
        self.assertContains(response, "2 KG")
        self.assertContains(response, "Add to cart")

    def test_quick_view_keeps_selected_variant_details_together(self):
        item = product(price=Decimal("999.00"), original_price=Decimal("1099.00"))
        expensive = ProductVariant.objects.create(
            product=item,
            size="3 KG",
            price=Decimal("2130.00"),
            original_price=Decimal("2300.00"),
            stock=19,
            external_image_url="https://example.com/3kg.jpg",
        )
        selected = ProductVariant.objects.create(
            product=item,
            size="1.5 KG",
            price=Decimal("1180.00"),
            original_price=Decimal("1250.00"),
            stock=7,
            external_image_url="https://example.com/1-5kg.jpg",
        )

        response = self.client.get(reverse("quick_view", args=[item.id]))
        html = response.content.decode()

        self.assertContains(response, "₹1180.00")
        self.assertContains(response, "7 available")
        self.assertContains(response, 'src="https://example.com/1-5kg.jpg"')
        self.assertIn(
            f'value="{selected.id}" data-size="1.5 KG" data-price="1180.00" '
            'data-mrp="1250.00" data-stock="7" data-image="https://example.com/1-5kg.jpg" checked',
            html,
        )
        self.assertIn(
            f'value="{expensive.id}" data-size="3 KG" data-price="2130.00" '
            'data-mrp="2300.00" data-stock="19" data-image="https://example.com/3kg.jpg"',
            html,
        )

    def test_recent_deduplicates_orders_and_excludes_unavailable(self):
        first, second = product("First"), product("Second")
        session = self.client.session
        class Request: pass
        request = Request(); request.session = session
        remember_recently_viewed(request, first.id); remember_recently_viewed(request, second.id); remember_recently_viewed(request, first.id)
        session.save()
        request.session = self.client.session
        self.assertEqual([p.id for p in recently_viewed(request)], [first.id, second.id])
        first.is_available = False; first.save(update_fields=["is_available"])
        self.assertEqual([p.id for p in recently_viewed(request)], [second.id])


@override_settings(STORAGES=LOCAL_STORAGES)
class RecommendationAndOfferTests(TestCase):
    def test_valid_orders_rank_and_invalid_orders_do_not(self):
        anchor, valid, invalid = product("Anchor"), product("Valid Pair"), product("Invalid Pair")
        good = Order.objects.create(customer_name="A", email="a@x.com", phone="1", address="x", status="delivered", payment_status="paid")
        bad = Order.objects.create(customer_name="B", email="b@x.com", phone="1", address="x", status="cancelled", payment_status="failed")
        for order, pair in ((good, valid), (bad, invalid)):
            OrderItem.objects.create(order=order, product=anchor, quantity=1, price=100)
            OrderItem.objects.create(order=order, product=pair, quantity=1, price=100)
        picks = frequently_bought(anchor)
        self.assertEqual(picks[0], valid)

    def test_cat_product_is_not_recommended_to_dog(self):
        anchor = product("Anchor")
        cat = product("Cat Food", category="cat_food", pet_type="cat")
        order = Order.objects.create(customer_name="A", email="a@x.com", phone="1", address="x", status="delivered", payment_status="paid")
        OrderItem.objects.create(order=order, product=anchor, quantity=1, price=100)
        OrderItem.objects.create(order=order, product=cat, quantity=1, price=100)
        self.assertNotIn(cat, frequently_bought(anchor))

    def test_active_offer_appears_and_expired_is_hidden(self):
        item = product()
        active = OfferCampaign.objects.create(title="Active", slug="active")
        active.products.add(item)
        OfferCampaign.objects.create(title="Old", slug="old", ends_at=timezone.now() - timedelta(days=1))
        response = self.client.get(reverse("offers"))
        self.assertContains(response, "Active")
        self.assertNotContains(response, "Old")


class BundleTests(TestCase):
    def test_bundle_price_and_stock_validation(self):
        item = product()
        bundle = ProductBundle.objects.create(name="Starter", slug="starter", bundle_price=Decimal("80.00"))
        BundleItem.objects.create(bundle=bundle, product=item, quantity=2)
        snapshot = bundle_snapshot(bundle)
        self.assertEqual(snapshot["price"], Decimal("80.00"))
        self.assertTrue(snapshot["available"])
        item.stock = 1; item.save(update_fields=["stock"])
        self.assertFalse(bundle_snapshot(bundle)["available"])

    def test_available_bundle_adds_component_to_cart(self):
        item = product()
        bundle = ProductBundle.objects.create(name="Starter", slug="starter", bundle_price=Decimal("80.00"))
        BundleItem.objects.create(bundle=bundle, product=item, quantity=1)
        self.client.post(reverse("add_bundle", args=[bundle.slug]))
        line = next(iter(self.client.session["cart"].values()))
        self.assertEqual(line["bundle_id"], bundle.id)

    def test_cart_reprices_bundle_from_current_server_data(self):
        item = product(price=Decimal("100.00"))
        bundle = ProductBundle.objects.create(name="Starter", slug="starter", bundle_price=Decimal("80.00"))
        BundleItem.objects.create(bundle=bundle, product=item, quantity=1)
        self.client.post(reverse("add_bundle", args=[bundle.slug]))

        bundle.bundle_price = Decimal("60.00")
        bundle.save(update_fields=["bundle_price"])
        response = self.client.get(reverse("cart"))

        self.assertEqual(response.context["subtotal"], Decimal("60.00"))

    def test_expired_bundle_is_removed_from_cart(self):
        item = product()
        bundle = ProductBundle.objects.create(name="Starter", slug="starter", bundle_price=Decimal("80.00"))
        BundleItem.objects.create(bundle=bundle, product=item, quantity=1)
        self.client.post(reverse("add_bundle", args=[bundle.slug]))
        bundle.ends_at = timezone.now() - timedelta(seconds=1)
        bundle.save(update_fields=["ends_at"])

        response = self.client.get(reverse("cart"))

        self.assertEqual(response.context["cart_items"], [])
        self.assertFalse(self.client.session["cart"])


class BundleCrmSearchTests(TestCase):
    def setUp(self):
        staff = User.objects.create_user(username="bundle-manager", password="test-pass", is_staff=True)
        self.client.force_login(staff)

    def test_page_is_lightweight_and_search_finds_product_and_variant_sku(self):
        wanted = product("Royal Canin Mini Puppy")
        ProductVariant.objects.create(product=wanted, size="3 KG", price=90, stock=3, sku="RC-3KG")
        for index in range(30):
            product(f"Unrelated Food {index}")

        page = self.client.get(reverse("crm_bundles"))
        self.assertEqual(page.status_code, 200)
        self.assertNotContains(page, "Unrelated Food 29")

        results = self.client.get(reverse("crm_bundle_product_search"), {"q": "RC-3KG"}).json()["results"]
        self.assertEqual(results[0]["id"], wanted.id)
        variants = self.client.get(reverse("crm_bundle_variant_search"), {"product": wanted.id}).json()["results"]
        self.assertEqual(variants[0]["text"], "3 KG · RC-3KG · Stock 3")


@override_settings(STORAGES=LOCAL_STORAGES)
class PrescriptionTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user("owner", password="pass")
        self.other = User.objects.create_user("other", password="pass")
        self.staff = User.objects.create_user("staff", password="pass", is_staff=True)
        self.medicine = product("Medicine", category="dog_medicine", requires_prescription=True)

    def test_upload_and_checkout_cannot_bypass_approval(self):
        self.client.force_login(self.owner)
        upload = SimpleUploadedFile("rx.pdf", b"%PDF-1.4 safe", content_type="application/pdf")
        response = self.client.post(reverse("prescription_upload", args=[self.medicine.id]), {"file": upload})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Prescription.objects.get().status, "pending")
        self.client.post(reverse("add_to_cart", args=[self.medicine.id]))
        response = self.client.get(reverse("checkout"))
        self.assertRedirects(response, reverse("prescription_upload", args=[self.medicine.id]), fetch_redirect_response=False)

    def test_invalid_extension_rejected(self):
        self.client.force_login(self.owner)
        upload = SimpleUploadedFile("rx.exe", b"bad", content_type="application/octet-stream")
        response = self.client.post(reverse("prescription_upload", args=[self.medicine.id]), {"file": upload})
        self.assertContains(response, "JPG, JPEG, PNG or PDF")
        self.assertFalse(Prescription.objects.exists())

    def test_executable_disguised_as_pdf_is_rejected(self):
        self.client.force_login(self.owner)
        upload = SimpleUploadedFile("rx.pdf", b"MZ executable", content_type="application/pdf")
        response = self.client.post(reverse("prescription_upload", args=[self.medicine.id]), {"file": upload})
        self.assertContains(response, "not a valid PDF")
        self.assertFalse(Prescription.objects.exists())

    def test_other_user_cannot_download_and_staff_can_review(self):
        prescription = Prescription.objects.create(user=self.owner, product=self.medicine,
            file=SimpleUploadedFile("rx.pdf", b"%PDF-1.4", content_type="application/pdf"))
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(reverse("prescription_download", args=[prescription.id])).status_code, 403)
        self.client.force_login(self.staff)
        self.client.post(reverse("crm_prescription_review", args=[prescription.id]), {"action": "approved", "notes": "Clear"})
        prescription.refresh_from_db()
        self.assertEqual(prescription.status, "approved")
