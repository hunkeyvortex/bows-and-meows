import logging
from email.utils import parseaddr

import requests
from django.conf import settings
from django.core.mail.backends.base import BaseEmailBackend


logger = logging.getLogger(__name__)


class BrevoDeliveryError(RuntimeError):
    """A safe, actionable Brevo delivery error for production logs."""



class BrevoAPIEmailBackend(BaseEmailBackend):
    """Send Django email messages through Brevo's HTTPS transactional API.

    This backend is suitable for hosts that block outbound SMTP ports.  It
    intentionally follows Django's email-backend contract, so the rest of the
    application can continue using EmailMessage/EmailMultiAlternatives.
    """

    endpoint = "https://api.brevo.com/v3/smtp/email"

    def send_messages(self, email_messages):
        if not email_messages:
            return 0

        sent = 0
        for message in email_messages:
            try:
                self._send_message(message)
                sent += 1
            except Exception:
                if not self.fail_silently:
                    raise
        return sent

    def _send_message(self, message):
        api_key = getattr(settings, "BREVO_API_KEY", "").strip()
        if not api_key:
            raise RuntimeError("BREVO_API_KEY is not configured")

        sender_name, sender_email = parseaddr(
            message.from_email or getattr(settings, "DEFAULT_FROM_EMAIL", "")
        )
        sender_email = (
            getattr(settings, "BREVO_SENDER_EMAIL", "").strip()
            or sender_email
        )
        sender_name = (
            getattr(settings, "BREVO_SENDER_NAME", "").strip()
            or sender_name
            or "Boww & Meow"
        )
        if not sender_email:
            raise RuntimeError("BREVO_SENDER_EMAIL is not configured")

        html_content = None
        for content, mimetype in getattr(message, "alternatives", []):
            if mimetype == "text/html":
                html_content = content
                break

        payload = {
            "sender": {"name": sender_name, "email": sender_email},
            "to": [self._recipient(value) for value in message.to],
            "subject": message.subject,
            "textContent": message.body or "",
        }
        if html_content:
            payload["htmlContent"] = html_content
        if message.cc:
            payload["cc"] = [self._recipient(value) for value in message.cc]
        if message.bcc:
            payload["bcc"] = [self._recipient(value) for value in message.bcc]
        if message.reply_to:
            payload["replyTo"] = self._recipient(message.reply_to[0])

        try:
            response = requests.post(
                self.endpoint,
                json=payload,
                headers={
                    "accept": "application/json",
                    "api-key": api_key,
                    "content-type": "application/json",
                },
                timeout=getattr(settings, "EMAIL_TIMEOUT", 10),
            )
        except requests.RequestException as exc:
            raise BrevoDeliveryError(f"Brevo API connection failed: {exc}") from exc

        if not 200 <= response.status_code < 300:
            detail = (response.text or "No response body").strip()[:1000]
            raise BrevoDeliveryError(
                f"Brevo API returned HTTP {response.status_code}: {detail}"
            )

        try:
            message_id = response.json().get("messageId", "")
        except (TypeError, ValueError):
            message_id = ""
        logger.info("Brevo accepted transactional email%s", f" ({message_id})" if message_id else "")

    @staticmethod
    def _recipient(value):
        name, email = parseaddr(value)
        recipient = {"email": email or value}
        if name:
            recipient["name"] = name
        return recipient
