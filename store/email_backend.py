import ssl
from email.utils import parseaddr

import requests
from django.conf import settings
from django.core.mail.backends.base import BaseEmailBackend
from django.core.mail.backends.smtp import EmailBackend


class RelaxedStrictSMTPBackend(EmailBackend):

    @property
    def ssl_context(self):
        context = ssl.create_default_context()

        # Python 3.13+ enables strict X509 checking by default.
        # Remove only the strict flag.
        if hasattr(ssl, "VERIFY_X509_STRICT"):
            context.verify_flags &= ~ssl.VERIFY_X509_STRICT

        return context


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
        response.raise_for_status()

    @staticmethod
    def _recipient(value):
        name, email = parseaddr(value)
        recipient = {"email": email or value}
        if name:
            recipient["name"] = name
        return recipient
