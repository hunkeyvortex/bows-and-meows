from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Count, Q

from store.models import (
    Product,
    STOREFRONT_FOOD_CATEGORIES,
    STOREFRONT_PAUSED_CATEGORIES,
    STOREFRONT_PAUSED_PRODUCT_TYPES,
)


class Command(BaseCommand):
    help = (
        "Archive medicine, vaccination and accessory products while preserving "
        "food products and all historical records."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Apply the archive operation. Without this flag the command is a dry run.",
        )

    def handle(self, *args, **options):
        paused_match = Q(product_type__in=STOREFRONT_PAUSED_PRODUCT_TYPES) | Q(
            category__in=STOREFRONT_PAUSED_CATEGORIES
        )
        products = (
            Product.objects.filter(paused_match, is_archived=False)
            .exclude(product_type="food")
            .exclude(category__in=STOREFRONT_FOOD_CATEGORIES)
        )
        by_type = list(
            products.order_by()
            .values("product_type")
            .annotate(total=Count("id"))
            .order_by("product_type")
        )

        self.stdout.write(f"Products selected for archiving: {products.count()}")
        for item in by_type:
            self.stdout.write(f"  {item['product_type'] or '(blank)'}: {item['total']}")
        self.stdout.write("Food products selected: 0")

        if not options["apply"]:
            self.stdout.write("Dry run only. Add --apply to archive these products.")
            return

        with transaction.atomic():
            archived = products.update(is_archived=True)

        self.stdout.write(self.style.SUCCESS(
            f"Archived {archived} products. Records, images, variants and order history were preserved."
        ))
