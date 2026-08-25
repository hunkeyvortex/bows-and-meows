import re
from collections import defaultdict

from django.core.management.base import BaseCommand
from django.db import transaction

from store.models import Product, ProductVariant


def normalized(value):
    return re.sub(r"\s+", " ", str(value or "").strip()).casefold()


class Command(BaseCommand):
    help = "Preview or safely archive duplicate name/brand products under one canonical product."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--limit", type=int, default=0)

    def handle(self, *args, **options):
        groups = defaultdict(list)
        # Previously consolidated aliases remain in the database for history,
        # but must not be planned again on later cleanup runs.
        products = (
            Product.objects.filter(duplicate_of__isnull=True)
            .prefetch_related("variants")
            .order_by("id")
        )
        for product in products:
            key = (normalized(product.name), normalized(product.brand))
            if all(key):
                groups[key].append(product)

        duplicate_groups = [group for group in groups.values() if len(group) > 1]
        if options["limit"]:
            duplicate_groups = duplicate_groups[: options["limit"]]

        summary = {
            "duplicate_groups": len(duplicate_groups),
            "products_to_archive": sum(len(group) - 1 for group in duplicate_groups),
            "variants_to_move": 0,
            "variant_conflicts": 0,
        }

        plans = []
        for group in duplicate_groups:
            canonical = sorted(
                group,
                key=lambda product: (
                    product.is_archived,
                    not product.is_available,
                    -(product.stock or 0),
                    product.id,
                ),
            )[0]
            occupied_sizes = {
                normalized(variant.size) for variant in canonical.variants.all()
            }
            moves = []
            conflicts = []
            for duplicate in group:
                if duplicate.id == canonical.id:
                    continue
                for variant in duplicate.variants.all():
                    size_key = normalized(variant.size)
                    if size_key and size_key not in occupied_sizes:
                        occupied_sizes.add(size_key)
                        moves.append(variant)
                    else:
                        conflicts.append(variant)
            summary["variants_to_move"] += len(moves)
            summary["variant_conflicts"] += len(conflicts)
            plans.append((canonical, group, moves, conflicts))

        self.stdout.write(str(summary))
        for canonical, group, moves, conflicts in plans[:20]:
            self.stdout.write(
                f"keep #{canonical.id}; archive "
                f"{[product.id for product in group if product.id != canonical.id]}; "
                f"move {len(moves)} variants; conflicts {len(conflicts)}"
            )

        if not options["apply"]:
            self.stdout.write("Dry run only. Add --apply after reviewing this report.")
            return

        with transaction.atomic():
            for canonical, group, moves, conflicts in plans:
                for variant in moves:
                    variant.product = canonical
                    variant.save(update_fields=["product"])
                if conflicts:
                    ProductVariant.objects.filter(
                        id__in=[variant.id for variant in conflicts]
                    ).update(stock=0, is_available=False)
                duplicates = [product for product in group if product.id != canonical.id]
                Product.objects.filter(id__in=[product.id for product in duplicates]).update(
                    is_archived=True,
                    is_available=False,
                    stock=0,
                    duplicate_of=canonical,
                )
                total_stock = sum(
                    variant.stock
                    for variant in canonical.variants.filter(is_available=True, stock__gt=0)
                )
                if canonical.variants.exists():
                    canonical.stock = total_stock
                    canonical.is_available = total_stock > 0
                    canonical.save(update_fields=["stock", "is_available"])

        self.stdout.write(self.style.SUCCESS("Duplicate products archived; no products were deleted."))
