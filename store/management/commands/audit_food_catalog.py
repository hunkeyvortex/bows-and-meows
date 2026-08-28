import csv
import re
from collections import defaultdict
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.parse import urlsplit

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Q

from store.models import Product, ProductVariant


FOOD_CATEGORIES = ("dog_food", "cat_food")

DOG_TOP_FIVE = (
    "Pedigree Adult Chicken & Vegetables Dry Dog Food",
    "Drools Adult Chicken & Egg Dry Dog Food",
    "Royal Canin Maxi Adult Dry Dog Food",
    "Pedigree Adult Meat & Rice Dry Dog Food",
    "Farmina N&D Pumpkin Chicken & Pomegranate Adult Dog Food",
)

CAT_TOP_FIVE = (
    "Royal Canin Persian Adult Dry Cat Food",
    "Whiskas Adult Ocean Fish Dry Cat Food",
    "Me-O Persian Adult Cat Food",
    "Purepet Adult Ocean Fish Dry Cat Food",
    "Royal Canin Persian Kitten Dry Cat Food",
)

# Deliberately conservative. These terms identify items that cannot reasonably
# be food. Borderline names are reported nowhere and remain untouched for staff
# review rather than risking a legitimate diet product.
NON_FOOD_NAME_RE = re.compile(
    r"\b(?:"
    r"t[ -]?shirt|shirt|sherwani|kurta|hoodie|sweater|jacket|dress|"
    r"raincoat|bandana|sock|shoe|collar|leash|harness|muzzle|carrier|"
    r"crate|cage|toy|ball|frisbee|bed|bowl|mat|diaper|training pad|"
    r"shampoo|conditioner|lotion|ointment|tablet|capsule|syrup|"
    r"injection|vaccine|wipes?|dental paste|ear cleaner|eye drops?|"
    r"supplements?|multivitamins?"
    r")\b",
    re.IGNORECASE,
)


def normalized_identity(value):
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").casefold()).strip()


def normalized_size(value):
    text = str(value or "").casefold().strip()
    replacements = (
        (r"kilograms?", "kg"), (r"kgs?\b", "kg"),
        (r"grams?", "g"), (r"gms?\b", "g"),
        (r"millilit(?:er|re)s?", "ml"), (r"mls?\b", "ml"),
        (r"lit(?:er|re)s?", "l"), (r"ltrs?\b", "l"),
    )
    for pattern, replacement in replacements:
        text = re.sub(pattern, replacement, text)
    return re.sub(r"[^a-z0-9.]+", "", text)


def valid_url(value):
    if not value or len(value) > 1000:
        return False
    return urlsplit(value).scheme in {"http", "https"}


def as_money(value):
    try:
        return Decimal(str(value or "")).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        return None


class Command(BaseCommand):
    help = (
        "Audit food catalogue quality and optionally apply conservative, "
        "history-safe fixes. Dry-run is the default."
    )

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true")
        parser.add_argument(
            "--catalog",
            default=str(
                settings.BASE_DIR
                / "catalog_exports"
                / "full"
                / "supertails_bulk_import.csv"
            ),
        )

    def handle(self, *args, **options):
        products = list(
            Product.objects.filter(
                category__in=FOOD_CATEGORIES,
                is_archived=False,
            )
            .prefetch_related("variants")
            .order_by("id")
        )

        catalog_by_product = {}
        catalog_by_identity = {}
        catalog_path = Path(options["catalog"])
        if catalog_path.exists():
            wanted_supplier_ids = {
                product.supplier_product_id
                for product in products
                if product.supplier_product_id
            }
            wanted_identities = {
                (
                    normalized_identity(product.name),
                    normalized_identity(product.brand),
                )
                for product in products
            }
            with catalog_path.open(encoding="utf-8-sig", newline="") as source:
                for row in csv.DictReader(source):
                    supplier_id = str(
                        row.get("supertails_product_id")
                        or row.get("product_code")
                        or ""
                    ).strip()
                    identity = (
                        normalized_identity(row.get("name")),
                        normalized_identity(row.get("brand")),
                    )
                    if supplier_id in wanted_supplier_ids:
                        catalog_by_product.setdefault(supplier_id, row)
                    if identity in wanted_identities:
                        catalog_by_identity.setdefault(identity, row)

        all_products_by_identity = defaultdict(list)
        for product in Product.objects.only(
            "id", "name", "brand", "image", "external_image_url"
        ).iterator():
            all_products_by_identity[
                (
                    normalized_identity(product.name),
                    normalized_identity(product.brand),
                )
            ].append(product)

        archive_products = []
        invalid_products = []
        duplicate_variant_groups = []
        invalid_variants = []
        invalid_product_mrps = []
        invalid_variant_mrps = []
        image_repairs = []
        unresolved_images = []
        parent_syncs = []

        for product in products:
            if NON_FOOD_NAME_RE.search(product.name or ""):
                archive_products.append(product)
                continue

            variants = list(product.variants.all())
            groups = defaultdict(list)
            for variant in variants:
                groups[normalized_size(variant.size)].append(variant)

            disabled_ids = set()
            for size_key, group in groups.items():
                active = [
                    variant
                    for variant in group
                    if variant.is_available and variant.stock > 0
                ]
                if not size_key or len(active) < 2:
                    continue
                canonical = sorted(
                    active,
                    key=lambda variant: (
                        variant.price <= 0,
                        # The oldest row is the staff-curated/original variant
                        # in this catalogue. Newer duplicate imports must not
                        # silently replace its price with a later supplier
                        # snapshot. Any useful duplicate image is copied below.
                        variant.id,
                    ),
                )[0]
                duplicates = [variant for variant in active if variant.id != canonical.id]
                duplicate_variant_groups.append((product, canonical, duplicates))
                disabled_ids.update(variant.id for variant in duplicates)

            for variant in variants:
                if variant.price <= 0 and variant.is_available:
                    invalid_variants.append(variant)
                    disabled_ids.add(variant.id)
                if variant.original_price is not None and variant.original_price <= variant.price:
                    invalid_variant_mrps.append(variant)

            remaining = [
                variant
                for variant in variants
                if variant.is_available
                and variant.stock > 0
                and variant.price > 0
                and variant.id not in disabled_ids
            ]
            if variants:
                total_stock = sum(variant.stock for variant in remaining)
                if remaining:
                    cheapest = sorted(remaining, key=lambda variant: (variant.price, variant.id))[0]
                    target_price = cheapest.price
                    target_mrp = (
                        cheapest.original_price
                        if cheapest.original_price and cheapest.original_price > cheapest.price
                        else None
                    )
                else:
                    target_price = product.price
                    target_mrp = (
                        product.original_price
                        if product.original_price and product.original_price > product.price
                        else None
                    )
                target_available = total_stock > 0
                if (
                    product.stock != total_stock
                    or product.is_available != target_available
                    or (remaining and product.price != target_price)
                    or (remaining and product.original_price != target_mrp)
                ):
                    parent_syncs.append(
                        (product, total_stock, target_available, target_price, target_mrp)
                    )
            elif product.price <= 0 and product.is_available:
                invalid_products.append(product)

            if product.original_price is not None and product.original_price <= product.price:
                invalid_product_mrps.append(product)

            if not (product.image or product.external_image_url):
                source_kind = ""
                source_value = ""
                source_image = None
                for variant in variants:
                    if variant.image:
                        source_kind = "variant-image"
                        source_image = variant.image.name
                        break
                    if valid_url(variant.external_image_url):
                        source_kind = "variant-url"
                        source_value = variant.external_image_url
                        break

                if not source_kind:
                    identity = (
                        normalized_identity(product.name),
                        normalized_identity(product.brand),
                    )
                    for duplicate in all_products_by_identity.get(identity, ()):
                        if duplicate.id == product.id:
                            continue
                        if duplicate.image:
                            source_kind = "matching-product-image"
                            source_image = duplicate.image.name
                            break
                        if valid_url(duplicate.external_image_url):
                            source_kind = "matching-product-url"
                            source_value = duplicate.external_image_url
                            break

                if not source_kind:
                    row = catalog_by_product.get(product.supplier_product_id)
                    if not row:
                        row = catalog_by_identity.get(
                            (
                                normalized_identity(product.name),
                                normalized_identity(product.brand),
                            )
                        )
                    candidate = str((row or {}).get("product_image_url") or "").strip()
                    if valid_url(candidate):
                        source_kind = "supplier-catalog-url"
                        source_value = candidate

                if source_kind:
                    image_repairs.append(
                        (product, source_kind, source_image, source_value)
                    )
                else:
                    unresolved_images.append(product)

        visible = Product.objects.customer_visible()
        ranking_status = {}
        for pet, category, names in (
            ("dog", "dog_food", DOG_TOP_FIVE),
            ("cat", "cat_food", CAT_TOP_FIVE),
        ):
            present = set(
                visible.filter(category=category, name__in=names)
                .values_list("name", flat=True)
            )
            ranking_status[pet] = {
                "ready": [name for name in names if name in present],
                "missing": [name for name in names if name not in present],
            }

        summary = {
            "food_products_checked": len(products),
            "incorrectly_categorised_to_archive": len(archive_products),
            "duplicate_variant_groups": len(duplicate_variant_groups),
            "duplicate_variants_to_disable": sum(
                len(duplicates)
                for _product, _canonical, duplicates in duplicate_variant_groups
            ),
            "invalid_product_prices_to_archive": len(invalid_products),
            "invalid_variant_prices_to_disable": len(invalid_variants),
            "invalid_product_mrps_to_clear": len(invalid_product_mrps),
            "invalid_variant_mrps_to_clear": len(invalid_variant_mrps),
            "parent_price_stock_syncs": len(parent_syncs),
            "missing_images_to_repair": len(image_repairs),
            "missing_images_unresolved": len(unresolved_images),
        }
        self.stdout.write(str(summary))

        for product in archive_products:
            self.stdout.write(f"ARCHIVE non-food #{product.id}: {product.name}")
        for product, canonical, duplicates in duplicate_variant_groups:
            self.stdout.write(
                f"DEDUP #{product.id} {product.name!r} size {canonical.size!r}: "
                f"keep variant #{canonical.id} (INR {canonical.price}, stock {canonical.stock}); "
                f"disable {[(v.id, str(v.price), v.stock) for v in duplicates]}"
            )
        for product, source_kind, _source_image, _source_value in image_repairs:
            self.stdout.write(
                f"IMAGE #{product.id} {product.name!r}: use {source_kind}"
            )
        for product in unresolved_images:
            self.stdout.write(f"IMAGE UNRESOLVED #{product.id}: {product.name}")
        self.stdout.write(f"TOP FIVE: {ranking_status}")

        if not options["apply"]:
            self.stdout.write("Dry run only. Add --apply after reviewing this report.")
            return

        with transaction.atomic():
            Product.objects.filter(
                id__in=[product.id for product in archive_products + invalid_products]
            ).update(is_archived=True, is_available=False)

            for _product, canonical, duplicates in duplicate_variant_groups:
                for duplicate in duplicates:
                    if not (canonical.image or canonical.external_image_url):
                        if duplicate.image:
                            canonical.image.name = duplicate.image.name
                        elif duplicate.external_image_url:
                            canonical.external_image_url = duplicate.external_image_url
                    canonical.save(update_fields=["image", "external_image_url"])
                ProductVariant.objects.filter(
                    id__in=[variant.id for variant in duplicates]
                ).update(stock=0, is_available=False)

            ProductVariant.objects.filter(
                id__in=[variant.id for variant in invalid_variants]
            ).update(stock=0, is_available=False)
            ProductVariant.objects.filter(
                id__in=[variant.id for variant in invalid_variant_mrps]
            ).update(original_price=None)
            Product.objects.filter(
                id__in=[product.id for product in invalid_product_mrps]
            ).update(original_price=None)

            for product, total_stock, available, price, mrp in parent_syncs:
                if product.id in {
                    archived.id for archived in archive_products + invalid_products
                }:
                    continue
                product.stock = total_stock
                product.is_available = available
                product.price = price
                product.original_price = mrp
                product.save(
                    update_fields=["stock", "is_available", "price", "original_price"]
                )

            for product, _source_kind, source_image, source_value in image_repairs:
                if source_image:
                    product.image.name = source_image
                else:
                    product.external_image_url = source_value
                product.save(update_fields=["image", "external_image_url"])

        self.stdout.write(self.style.SUCCESS(
            "Food catalogue cleanup applied. No products or order history were deleted."
        ))
