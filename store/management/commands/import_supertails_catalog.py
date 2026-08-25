import csv
from collections import defaultdict
from decimal import Decimal, InvalidOperation
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from store.models import Product, ProductVariant


def money(value, fallback="0.00"):
    try:
        return Decimal(str(value or fallback)).quantize(Decimal("0.01"))
    except InvalidOperation:
        return Decimal(fallback)


def clean(value, limit=None):
    result = str(value or "").strip()
    return result[:limit] if limit else result


def product_type_for(category):
    if category == "medicine":
        return "medicine"
    if category in {"supplement", "skin_coat", "dental", "joint_care", "digestive", "bird_supplement"}:
        return "supplement"
    if "groom" in category or category in {"hygiene", "training_pads"}:
        return "grooming"
    if "treat" in category:
        return "treat"
    if "food" in category:
        return "food"
    return "supply"


def pet_type_for(category, supplied_pet_type):
    """Infer only missing values; never overwrite an explicit supplier value."""
    supplied = clean(supplied_pet_type, 15)
    if supplied:
        return supplied
    if category.startswith("dog_"):
        return "dog"
    if category.startswith("cat_"):
        return "cat"
    if category.startswith("bird_"):
        return "bird"
    if category == "exotic_health":
        return "exotic"
    return "both"


class Command(BaseCommand):
    help = "Bulk upsert the complete Supertails CSV catalog with externally hosted supplier imagery."

    def add_arguments(self, parser):
        parser.add_argument(
            "--catalog",
            default=str(settings.BASE_DIR / "catalog_exports" / "full" / "supertails_bulk_import.csv"),
        )
        parser.add_argument(
            "--stock",
            type=int,
            default=0,
            help="Verified stock assigned to each imported variant (default: 0).",
        )
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        path = Path(options["catalog"])
        stock = max(0, options["stock"])
        if not path.exists():
            raise CommandError(f"Catalog not found: {path}")

        grouped = defaultdict(list)
        with path.open(encoding="utf-8-sig", newline="") as source:
            for row in csv.DictReader(source):
                supplier_id = clean(row.get("supertails_product_id")) or clean(row.get("product_code"))
                if row.get("name") and supplier_id:
                    grouped[supplier_id].append(row)

        self.stdout.write(f"Loaded {len(grouped)} products from {path.name}.")

        existing_products = list(Product.objects.all().order_by("id"))
        by_supplier = {p.supplier_product_id: p for p in existing_products if p.supplier_product_id}
        by_identity = {}
        for existing in existing_products:
            if not existing.supplier_product_id:
                by_identity.setdefault(
                    (existing.name.casefold(), existing.brand.casefold()), existing
                )
        product_updates = []
        product_creates = []

        for supplier_id, rows in grouped.items():
            row = rows[0]
            name = clean(row.get("name"), 200)
            brand = clean(row.get("brand"), 100)
            product = by_supplier.get(supplier_id)
            if product and product.duplicate_of_id:
                product = product.duplicate_of
            if not product:
                identity_match = by_identity.get((name.casefold(), brand.casefold()))
                # Only claim a legacy/manual product once. Two supplier records
                # can legitimately share a title and brand but still need
                # separate supplier identities and variant sets.
                if identity_match and not identity_match.supplier_product_id:
                    product = identity_match
            category = clean(row.get("category"), 50) or "accessory"
            values = {
                "name": name,
                "brand": brand,
                "pet_type": pet_type_for(category, row.get("pet_type")),
                "category": category,
                "life_stage": clean(row.get("life_stage"), 20) or "all",
                "flavour": clean(row.get("flavour"), 100),
                "description": clean(row.get("description")),
                "key_benefits": clean(row.get("key_benefits")).replace(" | ", "\n"),
                "price": money(row.get("base_price")),
                "original_price": money(row.get("base_mrp")) if row.get("base_mrp") else None,
                "stock": stock * len(rows),
                "product_type": product_type_for(category),
                "requires_prescription": category == "medicine",
                "is_available": stock > 0,
                "is_archived": False,
                "external_image_url": clean(row.get("product_image_url"), 1000),
                "source_url": clean(row.get("source_url"), 1000),
                "supplier_product_id": (
                    product.supplier_product_id
                    if product and product.supplier_product_id
                    else clean(supplier_id, 80)
                ),
            }
            if product:
                for field, value in values.items():
                    setattr(product, field, value)
                product_updates.append(product)
            else:
                product_creates.append(Product(**values))

        update_fields = [
            "name", "brand", "pet_type", "category", "life_stage", "flavour",
            "description", "key_benefits", "price", "original_price", "stock",
            "product_type", "requires_prescription", "is_available", "is_archived",
            "external_image_url", "source_url", "supplier_product_id",
        ]

        if options["dry_run"]:
            existing_variants = list(ProductVariant.objects.all())
            supplier_variant_ids = {
                variant.supplier_variant_id
                for variant in existing_variants
                if variant.supplier_variant_id
            }
            skus = {variant.sku for variant in existing_variants if variant.sku}
            variant_updates = 0
            variant_creates = 0
            seen_rows = set()
            skipped_rows = 0
            for rows in grouped.values():
                for row in rows:
                    identity = (
                        clean(row.get("supertails_variant_id"), 80),
                        clean(row.get("sku"), 100),
                    )
                    if identity in seen_rows:
                        skipped_rows += 1
                        continue
                    seen_rows.add(identity)
                    if identity[0] in supplier_variant_ids or identity[1] in skus:
                        variant_updates += 1
                    else:
                        variant_creates += 1
            self.stdout.write(str({
                "products_create": len(product_creates),
                "products_update": len(product_updates),
                "variants_create": variant_creates,
                "variants_update": variant_updates,
                "duplicates_or_skipped": skipped_rows,
            }))
            self.stdout.write("Dry run only. Remove --dry-run to apply the import.")
            return

        with transaction.atomic():
            if product_creates:
                Product.objects.bulk_create(product_creates, batch_size=500)
            if product_updates:
                Product.objects.bulk_update(product_updates, update_fields, batch_size=500)

        self.stdout.write(f"Products created: {len(product_creates)}; updated: {len(product_updates)}")
        product_map = {}
        for stored_product in Product.objects.exclude(supplier_product_id="").select_related("duplicate_of"):
            product_map[stored_product.supplier_product_id] = stored_product.duplicate_of or stored_product

        existing_variants = list(ProductVariant.objects.select_related("product").all())
        by_variant_supplier = {v.supplier_variant_id: v for v in existing_variants if v.supplier_variant_id}
        by_sku = {v.sku: v for v in existing_variants if v.sku}
        claimed_skus = set(by_sku)
        variant_creates = []
        variant_updates = []

        for supplier_product_id, rows in grouped.items():
            product = product_map[supplier_product_id]
            for index, row in enumerate(rows, start=1):
                supplier_variant_id = clean(row.get("supertails_variant_id"), 80)
                requested_sku = clean(row.get("sku"), 100)
                variant = by_variant_supplier.get(supplier_variant_id) if supplier_variant_id else None
                if not variant and requested_sku:
                    candidate = by_sku.get(requested_sku)
                    if candidate and candidate.product_id == product.id:
                        variant = candidate

                if variant:
                    sku = variant.sku or requested_sku
                else:
                    sku = requested_sku
                    if not sku or sku in claimed_skus:
                        sku = f"ST-{supplier_product_id}-{supplier_variant_id or index}"[:100]
                        suffix = 1
                        base = sku[:94]
                        while sku in claimed_skus:
                            suffix += 1
                            sku = f"{base}-{suffix}"[:100]
                    claimed_skus.add(sku)

                values = {
                    "product": product,
                    "size": clean(row.get("size"), 50) or "Standard",
                    "price": money(row.get("variant_price") or row.get("base_price")),
                    "original_price": money(row.get("variant_mrp")) if row.get("variant_mrp") else None,
                    "stock": stock,
                    "sku": sku,
                    "is_available": stock > 0,
                    "external_image_url": clean(row.get("variant_image_url") or row.get("product_image_url"), 1000),
                    "supplier_variant_id": supplier_variant_id,
                }
                if variant:
                    for field, value in values.items():
                        setattr(variant, field, value)
                    variant_updates.append(variant)
                else:
                    variant_creates.append(ProductVariant(**values))

        variant_fields = [
            "product", "size", "price", "original_price", "stock", "sku",
            "is_available", "external_image_url", "supplier_variant_id",
        ]
        with transaction.atomic():
            if variant_creates:
                ProductVariant.objects.bulk_create(variant_creates, batch_size=1000)
            if variant_updates:
                ProductVariant.objects.bulk_update(variant_updates, variant_fields, batch_size=1000)

        self.stdout.write(self.style.SUCCESS(
            f"Variants created: {len(variant_creates)}; updated: {len(variant_updates)}. Catalog is available."
        ))
