import json
from pathlib import Path
from datetime import datetime
from django.core.management.base import BaseCommand
from django.db import transaction
from store.models import Product
from store.catalog_sections import paused_catalog_query


class Command(BaseCommand):
    help = "Reversibly archive clothing and all medicines; dry run by default."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true")

    def handle(self, *args, **options):
        with transaction.atomic():
            products = Product.objects.filter(paused_catalog_query(), is_archived=False)
            if options["apply"]:
                products = products.select_for_update()
            rows = list(products.values("id", "name", "category", "product_type", "is_archived"))
            self.stdout.write(f"Selected {len(rows)} clothing/medicine records")
            folder = Path("catalog_exports")
            folder.mkdir(exist_ok=True)
            path = folder / ("archive-review-" + datetime.now().strftime("%Y%m%d-%H%M%S") + ".json")
            path.write_text(json.dumps(rows, indent=2), encoding="utf-8")
            self.stdout.write(f"Review/restore record: {path}")
            if options["apply"]:
                count = Product.objects.filter(id__in=[r["id"] for r in rows]).update(is_archived=True)
                self.stdout.write(f"Archived {count}; product data and order history preserved.")
            else:
                self.stdout.write("Dry run: no records changed.")
