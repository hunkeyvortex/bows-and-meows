from unittest.mock import Mock, patch

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
        post.return_value = Mock()

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

