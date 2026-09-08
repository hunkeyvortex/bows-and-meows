from unittest.mock import patch

from django.contrib.auth.models import User
from django.core import mail
from django.test import TransactionTestCase, override_settings
from django.db import transaction
from django.template.loader import get_template
from django.template.loader import render_to_string
from django.urls import reverse

from .models import Order, OrderItem, Product, OrderEmailDelivery, DeliveryZone
from .services.order_notifications import (
    notify_order_confirmed,
    notify_order_status,
    notify_payment_confirmed,
    notify_payment_failed,
    notify_owner_new_order,
    _context,
    _public_image_url,
    EVENT_CONFIG,
)


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    DEFAULT_FROM_EMAIL="Boww & Meow <orders@bowwandmeow.com>",
    ORDER_NOTIFICATION_EMAIL="owner@example.com",
    STOREFRONT_BASE_URL="https://shop.example.com",
    SUPPORT_EMAIL="care@example.com",
)
class OrderNotificationTests(TransactionTestCase):
    def setUp(self):
        self.customer = User.objects.create_user("customer", "customer@example.com", "pass12345")
        self.staff = User.objects.create_user("staff", "staff@example.com", "pass12345", is_staff=True)
        self.product = Product.objects.create(
            name="Test Dog Food",
            price="499.00",
            stock=10,
            is_available=True,
        )
        self.order = Order.objects.create(
            user=self.customer,
            customer_name="Pet Parent",
            email="buyer@example.com",
            phone="9999999999",
            address="12 Pet Street, Mumbai",
            payment_method="cod",
            payment_status="pending",
            status="confirmed",
            subtotal_amount="499.00",
            total_amount="449.00",
            discount_amount="50.00",
            coupon_code="WELCOME",
        )
        OrderItem.objects.create(
            order=self.order,
            product=self.product,
            variant_size="1 kg",
            quantity=1,
            price="499.00",
        )

    def test_confirmation_has_customer_order_number_and_branded_html(self):
        self.assertTrue(notify_order_confirmed(self.order))
        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual(message.to, ["buyer@example.com"])
        self.assertEqual(message.from_email, "Boww & Meow <orders@bowwandmeow.com>")
        self.assertIn("BM-%04d" % self.order.pk, message.subject)
        self.assertIn("BM-%04d" % self.order.pk, message.body)
        self.assertIn("Boww &amp; Meow", message.alternatives[0].content)
        self.assertIn("1 kg", message.alternatives[0].content)

    def test_all_customer_templates_share_complete_safe_order_summary(self):
        self.product.external_image_url = "https://cdn.example.com/product.jpg"
        self.product.save()
        self.order.address = "12 Pet Street\nMumbai"
        for event, (_, template) in EVENT_CONFIG.items():
            self.order.status = event if event in {"confirmed", "packed", "shipped", "delivered", "cancelled"} else "pending"
            context = _context(self.order, event)
            html = render_to_string(f"store/emails/{template}.html", context)
            plain = render_to_string(f"store/emails/{template}.txt", context)
            for output in (html, plain):
                for expected in ("BM-%04d" % self.order.pk, "Test Dog Food", "1 kg", "499.00", "449.00", "50.00", self.order.get_status_display(), "care@example.com", context["track_url"], "Cash on Delivery"):
                    self.assertIn(expected, output)
                self.assertNotIn("/crm/", output)
                self.assertNotIn("/admin/", output)
            self.assertIn('src="https://cdn.example.com/product.jpg"', html)
            self.assertIn("12 Pet Street<br>Mumbai", html)
            self.assertIn('role="presentation"', html)
            self.assertNotIn("<script", html)
            self.assertNotIn("<table", plain)
            if event == "cancelled":
                self.assertNotIn("Current stage", html)
            elif context["progress_stages"]:
                self.assertEqual(html.count("Current stage"), 1)

    def test_payment_labels_use_status_not_online_method(self):
        self.order.payment_method = "online"
        for status, label in (("pending", "Payment pending"), ("paid", "Paid online"), ("failed", "Payment not completed"), ("refunded", "Refunded")):
            self.order.payment_status = status
            context = _context(self.order, "payment_confirmed")
            for suffix in ("html", "txt"):
                body = render_to_string(f"store/emails/payment_confirmed.{suffix}", context)
                self.assertIn(label, body)
                if status != "paid":
                    self.assertNotIn("Paid online", body)
                    self.assertNotIn("We have confirmed your payment", body)

    def test_public_images_and_guest_tracking_fallback(self):
        for unsafe in ("http://cdn.example.com/a.jpg", "https://localhost/a.jpg", "https://127.0.0.1/a.jpg", "https://192.168.1.1/a.jpg", "https://user:password@example.com/a.jpg", "//example.com/a.jpg", "javascript:alert(1)"):
            self.assertEqual(_public_image_url(unsafe), "")
        self.assertEqual(_public_image_url("/media/a.jpg"), "https://shop.example.com/media/a.jpg")
        with override_settings(STOREFRONT_BASE_URL="http://127.0.0.1:8000"):
            self.assertEqual(_public_image_url("/media/a.jpg"), "")
        self.order.user = None
        html = render_to_string("store/emails/order_confirmed.html", _context(self.order, "confirmed"))
        self.assertNotIn("Track your order", html)
        self.assertNotIn('width="56"', html)
        self.assertNotIn("/crm/", html)

    def test_customer_lifecycle_templates_send_for_real_transitions(self):
        expected = ["packed", "shipped", "delivered", "cancelled"]
        old = "confirmed"
        for status in expected:
            self.order.status = status
            self.order.save(update_fields=["status"])
            self.assertTrue(notify_order_status(self.order, old))
            old = status
        self.assertEqual(len(mail.outbox), 4)
        for message in mail.outbox:
            self.assertIn("BM-%04d" % self.order.pk, message.subject)

    def test_unchanged_status_does_not_resend(self):
        self.assertFalse(notify_order_status(self.order, "confirmed"))
        self.assertEqual(mail.outbox, [])

    def test_owner_separate_once_with_order_details(self):
        notify_owner_new_order(self.order)
        notify_owner_new_order(Order.objects.get(pk=self.order.pk))
        notify_order_confirmed(self.order)
        notify_order_confirmed(Order.objects.get(pk=self.order.pk))
        self.assertEqual(len(mail.outbox), 2)
        self.assertEqual(mail.outbox[0].to, ["owner@example.com"])
        self.assertEqual(mail.outbox[1].to, ["buyer@example.com"])
        for value in ("Pet Parent", "buyer@example.com", "9999999999", "12 Pet Street", "Test Dog Food", "1 kg", "449.00", "Cash on Delivery", "/crm/orders/"):
            self.assertIn(value, mail.outbox[0].body)

    def test_status_reentry_does_not_duplicate_email(self):
        self.order.status = "packed"
        notify_order_status(self.order, "confirmed")
        notify_order_status(self.order, "shipped")
        self.assertEqual(len(mail.outbox), 1)

    def test_rollback_does_not_send(self):
        try:
            with transaction.atomic():
                notify_owner_new_order(self.order)
                self.assertEqual(mail.outbox, [])
                raise ValueError("rollback")
        except ValueError:
            pass
        self.assertEqual(mail.outbox, [])
        self.assertEqual(OrderEmailDelivery.objects.count(), 0)

    @patch("store.services.order_notifications.render_to_string", side_effect=RuntimeError("private diagnostic"))
    def test_render_failure_safe_and_not_replayed(self, render):
        self.assertFalse(notify_order_confirmed(self.order))
        self.assertFalse(notify_order_confirmed(self.order))
        self.assertEqual(render.call_count, 1)
        self.assertEqual(OrderEmailDelivery.objects.get().state, "failed")

    @patch("store.services.order_notifications.EmailMultiAlternatives.send", side_effect=RuntimeError("secret sentinel"))
    def test_post_commit_failure_preserves_order_and_is_safe(self, send):
        with self.assertLogs("store.services.order_notifications", level="ERROR") as logs:
            with transaction.atomic():
                self.order.customer_name = "Committed customer"
                self.order.save()
                notify_order_confirmed(self.order)
                notify_owner_new_order(self.order)
        self.order.refresh_from_db()
        self.assertEqual(self.order.customer_name, "Committed customer")
        self.assertEqual(Order.objects.count(), 1)
        self.assertNotIn("secret sentinel", " ".join(logs.output))
        self.assertNotIn(self.order.email, " ".join(logs.output))
        self.assertEqual(send.call_count, 2)

    def _checkout(self):
        DeliveryZone.objects.create(pincode="400097", city="Mumbai", state="Maharashtra", cod_available=True)
        self.client.force_login(self.customer)
        self.client.post(reverse("add_to_cart", args=[self.product.pk]))
        self.client.get(reverse("checkout"))
        return self.client.post(reverse("checkout"), {
            "checkout_token": self.client.session["checkout_token"],
            "customer_name": "Test Buyer", "email": "checkout@example.com",
            "phone": "9999999999", "address": "Test address",
            "pincode": "400097", "payment_method": "cod",
        })

    def test_checkout_customer_and_owner_notifications_once(self):
        response = self._checkout()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(mail.outbox), 2)
        self.assertEqual({tuple(m.to) for m in mail.outbox}, {("owner@example.com",), ("checkout@example.com",)})
        self.client.get(response.url)
        self.client.get(response.url)
        self.assertEqual(len(mail.outbox), 2)

    @patch("store.services.order_notifications.EmailMultiAlternatives.send", side_effect=RuntimeError("send failed"))
    def test_checkout_commits_once_despite_email_failure(self, send):
        response = self._checkout()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Order.objects.count(), 2)  # fixture + one checkout
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 9)
        self.client.get(response.url)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 9)
        self.assertEqual(Order.objects.count(), 2)

    def test_payment_confirmed_and_failed_events(self):
        notify_payment_confirmed(self.order)
        notify_payment_failed(self.order)
        self.assertEqual(len(mail.outbox), 2)
        self.assertIn("Payment confirmed", mail.outbox[0].subject)
        self.assertIn("needs attention", mail.outbox[1].subject)

    @patch("store.services.order_notifications.EmailMultiAlternatives.send", side_effect=RuntimeError("SMTP down"))
    def test_email_failure_never_escapes(self, mocked_send):
        self.assertFalse(notify_order_confirmed(self.order))
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, "confirmed")

    def test_crm_packed_transition_sends_once_and_same_status_does_not_resend(self):
        self.client.force_login(self.staff)
        response = self.client.post(reverse("crm_order_status", args=[self.order.pk]), {"status": "packed"})
        self.assertRedirects(response, reverse("crm_orders"))
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, "packed")
        self.assertEqual(len(mail.outbox), 1)

        self.client.post(reverse("crm_order_status", args=[self.order.pk]), {"status": "packed"})
        self.assertEqual(len(mail.outbox), 1)

    def test_header_logo_is_a_home_link(self):
        response = self.client.get(reverse("home"))
        self.assertContains(response, 'class="v2-brand"')
        self.assertContains(response, f'href="{reverse("home")}"', count=None)
        self.assertContains(response, "boww-meow-coral-logo.png")

    def test_checkout_relies_only_on_global_django_message_renderer(self):
        base_source = get_template("store/base.html").template.source
        checkout_source = get_template("store/checkout.html").template.source
        self.assertIn("{% for message in messages %}", base_source)
        self.assertNotIn("{% for message in messages %}", checkout_source)
        self.assertNotIn("bm-checkout-messages", checkout_source)
