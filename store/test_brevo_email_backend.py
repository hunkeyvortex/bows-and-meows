from unittest.mock import Mock, patch

import requests
from django.core.mail import EmailMultiAlternatives
from django.test import SimpleTestCase, override_settings


@override_settings(
    EMAIL_BACKEND="store.email_backend.BrevoAPIEmailBackend",
    BREVO_API_KEY="test-api-key",
    BREVO_SENDER_EMAIL="bowsandmeows00@gmail.com",
    BREVO_SENDER_NAME="Boww & Meow",
    DEFAULT_FROM_EMAIL="Boww & Meow <bowsandmeows00@gmail.com>",
    EMAIL_TIMEOUT=10,
)
class BrevoAPIEmailBackendTests(SimpleTestCase):
    @patch("store.email_backend.requests.post")
    def test_sends_text_and_html_through_brevo_https_api(self, post):
        post.return_value = Mock(
            status_code=201,
            text='{"messageId":"test-id"}',
            json=Mock(return_value={"messageId": "test-id"}),
        )

        message = EmailMultiAlternatives(
            subject="Order confirmed",
            body="Your order is confirmed.",
            to=["Pet Parent <buyer@example.com>"],
        )
        message.attach_alternative("<p>Your order is confirmed.</p>", "text/html")

        self.assertEqual(message.send(), 1)
        post.assert_called_once()
        call = post.call_args
        self.assertEqual(call.kwargs["timeout"], 10)
        self.assertEqual(call.kwargs["headers"]["api-key"], "test-api-key")
        self.assertEqual(
            call.kwargs["json"]["sender"],
            {"name": "Boww & Meow", "email": "bowsandmeows00@gmail.com"},
        )
        self.assertEqual(
            call.kwargs["json"]["to"],
            [{"name": "Pet Parent", "email": "buyer@example.com"}],
        )
        self.assertIn("htmlContent", call.kwargs["json"])

    @patch("store.email_backend.requests.post")
    def test_failure_contains_safe_brevo_response_detail(self, post):
        post.return_value = Mock(
            status_code=401,
            text='{"message":"Key not found"}',
        )
        message = EmailMultiAlternatives(
            subject="Order confirmed",
            body="Your order is confirmed.",
            to=["buyer@example.com"],
        )

        with self.assertRaisesMessage(RuntimeError, "Brevo API returned HTTP 401"):
            message.send(fail_silently=False)

    @patch("store.email_backend.requests.post")
    def test_failure_can_remain_non_blocking(self, post):
        post.side_effect = requests.Timeout("timed out")
        message = EmailMultiAlternatives(
            subject="Order confirmed",
            body="Your order is confirmed.",
            to=["buyer@example.com"],
        )

        self.assertEqual(message.send(fail_silently=True), 0)
