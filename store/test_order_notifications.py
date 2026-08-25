from unittest.mock import patch

from django.contrib.auth.models import User
from django.core import mail
from django.test import TestCase, override_settings
from django.template.loader import get_template
from django.urls import reverse

from .models import Order, OrderItem, Product
from .services.order_notifications import (
    notify_order_confirmed,
    notify_order_status,
    notify_payment_confirmed,
    notify_payment_failed,
)


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    DEFAULT_FROM_EMAIL="Boww & Meow <orders@example.com>",
    STOREFRONT_BASE_URL="https://shop.example.com",
    SUPPORT_EMAIL="care@example.com",
)
class OrderNotificationTests(TestCase):
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
        self.assertIn("BM-%04d" % self.order.pk, message.subject)
        self.assertIn("BM-%04d" % self.order.pk, message.body)
        self.assertIn("Boww &amp; Meow", message.alternatives[0].content)
        self.assertIn("1 kg", message.alternatives[0].content)

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
