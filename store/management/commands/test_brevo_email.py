from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Send one transactional email through the configured Brevo API backend."

    def add_arguments(self, parser):
        parser.add_argument(
            "--to",
            required=True,
            help="Recipient email address for this explicit delivery test.",
        )

    def handle(self, *args, **options):
        expected_backend = "store.email_backend.BrevoAPIEmailBackend"
        if settings.EMAIL_BACKEND != expected_backend:
            raise CommandError(
                f"Brevo is not active. EMAIL_BACKEND is {settings.EMAIL_BACKEND!r}. "
                "Configure BREVO_API_KEY and restart the service."
            )
        if not settings.BREVO_API_KEY:
            raise CommandError("BREVO_API_KEY is empty.")
        if not settings.BREVO_SENDER_EMAIL:
            raise CommandError("BREVO_SENDER_EMAIL is empty.")

        message = EmailMultiAlternatives(
            subject="Boww & Meow email delivery test",
            body=(
                "Your Boww & Meow transactional email connection is working. "
                "You can now receive order and delivery updates."
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[options["to"]],
        )
        message.attach_alternative(
            "<h2>Boww &amp; Meow email is working</h2>"
            "<p>Your transactional email connection is ready for order and delivery updates.</p>",
            "text/html",
        )

        try:
            sent = message.send(fail_silently=False)
        except Exception as exc:
            raise CommandError(str(exc)) from exc
        if sent != 1:
            raise CommandError(f"Brevo did not accept the test email (sent={sent}).")

        self.stdout.write(
            self.style.SUCCESS(f"Brevo accepted the test email for {options['to']}.")
        )
