import csv
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from store.models import Product, ProductImage


class Command(BaseCommand):
    help = "Bulk import all externally hosted Supertails gallery images."

    def add_arguments(self, parser):
        parser.add_argument(
            "--gallery",
            default=str(settings.BASE_DIR / "catalog_exports" / "full" / "supertails_gallery_images.csv"),
        )

    def handle(self, *args, **options):
        path = Path(options["gallery"])
        if not path.exists():
            raise CommandError(f"Gallery file not found: {path}")

        products_by_source = {
            product.source_url.rstrip("/"): product
            for product in Product.objects.exclude(source_url="")
        }
        existing = set(
            ProductImage.objects.exclude(external_image_url="")
            .values_list("product_id", "external_image_url")
        )
        creates = []
        skipped = 0

        with path.open(encoding="utf-8-sig", newline="") as source:
            for row in csv.DictReader(source):
                product = products_by_source.get(str(row.get("source_url") or "").rstrip("/"))
                image_url = str(row.get("image_url") or "").strip()[:1000]
                if not product or not image_url or (product.id, image_url) in existing:
                    skipped += 1
                    continue
                creates.append(ProductImage(
                    product=product,
                    external_image_url=image_url,
                    image_type="gallery",
                    sort_order=max(0, int(row.get("image_order") or 1) - 1),
                ))
                existing.add((product.id, image_url))

        ProductImage.objects.bulk_create(creates, batch_size=2000)
        self.stdout.write(self.style.SUCCESS(
            f"Gallery images created: {len(creates)}; skipped/already present: {skipped}."
        ))
