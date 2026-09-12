"""Read-only audit of the explicitly scoped placeholder-image products."""
import csv
import json
import os
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "petcare.settings")

import django

django.setup()

from django.db import connection, transaction
from store.models import Product


def main():
    with transaction.atomic():
        if connection.vendor == "postgresql":
            with connection.cursor() as cursor:
                cursor.execute("SET TRANSACTION READ ONLY")
        products = list(Product.objects.filter(
            is_available=True,
            is_archived=False,
            image__startswith="media/products/product-",
        ).prefetch_related("variants").order_by("pk"))
        rows = [{
            "product_id": p.pk,
            "brand": p.brand,
            "product_name": p.name,
            "category": p.category,
            "variants_sizes": json.dumps([
                {"variant_id": v.pk, "size": v.size}
                for v in p.variants.all()
            ], ensure_ascii=False),
            "current_image": p.image.name,
            "external_image_url": p.external_image_url,
            "source_url": p.source_url,
            "current_display_image_url": p.display_image_url,
        } for p in products]
        storage = Product._meta.get_field("image").storage
        print("Database engine:", connection.vendor)
        print("Image storage:", type(storage).__module__ + "." + type(storage).__name__)
        print("Target count:", len(rows))
        print("Brands:", json.dumps(dict(Counter(p.brand for p in products)), sort_keys=True))
        print("Targets with source URL:", sum(bool(p.source_url) for p in products))
        print("Targets with external image URL:", sum(bool(p.external_image_url) for p in products))
        print("Product 39:", json.dumps(next((r for r in rows if r["product_id"] == 39), None)))
    output = ROOT / "placeholder_product_scope_audit.csv"
    if output.exists():
        raise FileExistsError("Audit report already exists; refusing to overwrite")
    fields = ["product_id", "brand", "product_name", "category", "variants_sizes",
              "current_image", "external_image_url", "source_url", "current_display_image_url"]
    with output.open("x", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    print("Report:", output.name)
    if len(rows) != 64:
        print("STOP: target count differs from the expected 64. No records modified.")
        return 2
    return 0


if __name__ == "__main__":
    try:
        result = main()
    except Exception as exc:
        # Connection errors can contain credentials/host details; do not print them.
        print("Audit failed:", type(exc).__name__, "(connection details suppressed)")
        result = 1
    finally:
        connection.close()
    sys.exit(result)
