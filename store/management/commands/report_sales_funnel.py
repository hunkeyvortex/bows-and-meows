from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db.models import Count
from django.utils import timezone

from store.models import ConversionEvent


class Command(BaseCommand):
    help = "Report Boww & Meow funnel events and likely abandoned carts."

    def add_arguments(self, parser):
        parser.add_argument("--days", type=int, default=30)
        parser.add_argument(
            "--abandoned-after-hours",
            type=int,
            default=24,
            help="An add-to-cart session without a purchase after this age is abandoned.",
        )

    def handle(self, *args, **options):
        since = timezone.now() - timedelta(days=max(options["days"], 1))
        events = ConversionEvent.objects.filter(created_at__gte=since)
        counts = dict(events.values_list("event_type").annotate(total=Count("id")))

        self.stdout.write(f"Sales funnel — last {options['days']} day(s)")
        for event_type, label in ConversionEvent.EVENT_CHOICES:
            self.stdout.write(f"{label}: {counts.get(event_type, 0)}")

        cutoff = timezone.now() - timedelta(hours=max(options["abandoned_after_hours"], 1))
        cart_sessions = set(
            events.filter(event_type="add_to_cart", created_at__lte=cutoff)
            .exclude(session_key="")
            .values_list("session_key", flat=True)
        )
        purchased_sessions = set(
            events.filter(event_type="purchase_completed")
            .exclude(session_key="")
            .values_list("session_key", flat=True)
        )
        self.stdout.write(f"Likely abandoned carts: {len(cart_sessions - purchased_sessions)}")
