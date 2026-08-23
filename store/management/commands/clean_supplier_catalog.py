import csv
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from store.models import Product, ProductVariant


NON_RETAIL_TYPES = {
    "AHS Consumable",
    "Sample",
    "Services - Training",
    "Services - Vet",
}


class Command(BaseCommand):
    help = "Archive clear non-retail supplier records and remove unverified stock from new imports."

    def add_arguments(self, parser):
        parser.add_argument(
            "--catalog",
            default=str(settings.BASE_DIR / "catalog_exports" / "full" / "supertails_bulk_import.csv"),
        )
        parser.add_argument("--preserve-product-id-through", type=int, default=136)
        parser.add_argument("--apply", action="store_true")

    def handle(self, *args, **options):
        path = Path(options["catalog"])
        if not path.exists():
            raise CommandError(f"Catalog not found: {path}")

        non_retail_supplier_ids = set()
        with path.open(encoding="utf-8-sig", newline="") as source:
            for row in csv.DictReader(source):
                product_type = str(row.get("product_type") or "").strip()
                if product_type.startswith("Clinic ") or product_type in NON_RETAIL_TYPES:
                    supplier_id = str(row.get("supertails_product_id") or "").strip()
                    if supplier_id:
                        non_retail_supplier_ids.add(supplier_id)

        non_retail = Product.objects.filter(supplier_product_id__in=non_retail_supplier_ids)
        imported_retail = Product.objects.exclude(supplier_product_id="").exclude(
            supplier_product_id__in=non_retail_supplier_ids
        ).filter(id__gt=options["preserve_product_id_through"])

        summary = {
            "archive_products": non_retail.count(),
            "archive_variants": ProductVariant.objects.filter(product__in=non_retail).count(),
            "unverified_products": imported_retail.count(),
            "unverified_variants": ProductVariant.objects.filter(product__in=imported_retail).count(),
        }
        self.stdout.write(str(summary))
        if not options["apply"]:
            self.stdout.write("Dry run only. Add --apply to perform this cleanup.")
            return

        with transaction.atomic():
            ProductVariant.objects.filter(product__in=non_retail).update(stock=0, is_available=False)
            non_retail.update(stock=0, is_available=False, is_archived=True)

            ProductVariant.objects.filter(product__in=imported_retail).update(stock=0, is_available=False)
            imported_retail.update(stock=0, is_available=True, is_archived=False)

        self.stdout.write(self.style.SUCCESS(
            "Catalog cleanup applied. Original CRM inventory was preserved; new supplier stock now requires verification."
        ))
