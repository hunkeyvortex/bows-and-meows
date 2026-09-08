import json
import re
from difflib import SequenceMatcher
from pathlib import Path
from urllib.request import urlopen
from django.core.management.base import BaseCommand, CommandError
from store.models import Product


def normalized(value):
    return re.sub(r"[^a-z0-9]", "", value.lower())


class Command(BaseCommand):
    help = "Read Suryavets public availability and produce a catalogue comparison without modifying products."

    def handle(self, *args, **options):
        supplier = {}
        for page in range(1, 101):
            with urlopen(f"https://suryavets.com/products.json?limit=250&page={page}", timeout=30) as response:
                rows = json.load(response)["products"]
            if not rows:
                break
            before = len(supplier)
            supplier.update({p["id"]: p for p in rows})
            self.stdout.write(f"Read page {page}: {len(supplier)} products")
            self.stdout.flush()
            if len(supplier) == before:
                raise CommandError("Pagination repeated; refusing incomplete comparison")
        else:
            raise CommandError("Pagination limit reached")
        available = [p for p in supplier.values() if any(v.get("available") for v in p["variants"])]
        names = [(normalized(p["title"]), p) for p in available]
        folder = Path("catalog_exports/suryavets")
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "supplier.json").write_text(json.dumps(list(supplier.values()), indent=2), encoding="utf-8")
        result = []
        for product in Product.objects.filter(is_archived=False):
            name = normalized(product.name)
            candidates = [(n, p) for n, p in names if n[:4] == name[:4]]
            best = sorted(((SequenceMatcher(None, name, n).ratio(), p) for n, p in candidates), key=lambda x: x[0], reverse=True)[:3]
            result.append({"id": product.pk, "name": product.name, "visible": product.is_available,
                           "candidates": [{"score": round(score, 3), "title": p["title"], "handle": p["handle"]} for score, p in best]})
        folder = Path("catalog_exports/suryavets")
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "supplier.json").write_text(json.dumps(list(supplier.values()), indent=2), encoding="utf-8")
        (folder / "comparison.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        self.stdout.write(f"Supplier products: {len(supplier)}; available: {len(available)}; active local records: {len(result)}")
        for row in result:
            if row["visible"] and row["candidates"] and row["candidates"][0]["score"] >= .95:
                self.stdout.write(json.dumps(row))
