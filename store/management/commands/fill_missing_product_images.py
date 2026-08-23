import csv
import re
import textwrap
from io import BytesIO
from pathlib import Path

import requests
import truststore
from PIL import Image, ImageDraw, ImageFont
from django.conf import settings
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from django.db.models import Q

from store.models import Product


def normalize(value):
    return re.sub(r"[^a-z0-9]+", " ", (value or "").lower()).strip()


def tokens(value):
    return set(normalize(value).split())


def safe_filename(value):
    compact = re.sub(r"[^A-Za-z0-9_-]+", "-", value or "product").strip("-_")
    return (compact[:45] or "product") + ".jpg"


def font(size, bold=False):
    candidates = (
        "C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf",
        "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf",
    )
    for candidate in candidates:
        try:
            return ImageFont.truetype(candidate, size)
        except OSError:
            pass
    return ImageFont.load_default()


def branded_placeholder(product):
    canvas = Image.new("RGB", (900, 900), "#f7f6ef")
    draw = ImageDraw.Draw(canvas)

    draw.rounded_rectangle((38, 38, 862, 862), radius=44, fill="#ffffff", outline="#dfe5da", width=3)
    draw.ellipse((540, 65, 830, 355), fill="#edf5dc")
    draw.ellipse((70, 585, 315, 830), fill="#e5f1ec")

    # A restrained package silhouette creates a product-style visual without
    # pretending to be the supplier's exact packaging.
    draw.rounded_rectangle((270, 165, 630, 575), radius=34, fill="#1f5a40")
    draw.rounded_rectangle((294, 204, 606, 390), radius=22, fill="#f4f0db")
    draw.line((300, 495, 600, 495), fill="#a9c66f", width=8)
    draw.text((450, 273), (product.brand or "B&M")[:18].upper(), font=font(30, True), fill="#1d4d38", anchor="mm")
    draw.text((450, 440), "PET CARE", font=font(24, True), fill="#ffffff", anchor="mm")

    brand = (product.brand or "Bow & Meow").upper()
    draw.text((90, 625), brand[:35], font=font(24, True), fill="#6a8248")
    wrapped = textwrap.wrap(product.name.replace("�", "-"), width=35)[:3]
    draw.multiline_text((90, 670), "\n".join(wrapped), font=font(31, True), fill="#172b20", spacing=9)
    draw.text((90, 815), "PRODUCT IMAGE COMING SOON", font=font(16, True), fill="#7f8b83")

    output = BytesIO()
    canvas.save(output, format="JPEG", quality=90, optimize=True)
    return output.getvalue()


class Command(BaseCommand):
    help = "Attach supplier photos or professional branded placeholders to active products missing images."

    def add_arguments(self, parser):
        parser.add_argument(
            "--catalog",
            default=str(settings.BASE_DIR / "catalog_exports" / "full" / "supertails_bulk_import.csv"),
        )

    def handle(self, *args, **options):
        truststore.inject_into_ssl()
        catalog_path = Path(options["catalog"])
        if not catalog_path.exists():
            self.stderr.write(self.style.ERROR(f"Catalog not found: {catalog_path}"))
            return

        unique = {}
        with catalog_path.open(encoding="utf-8-sig", newline="") as source:
            for row in csv.DictReader(source):
                if row.get("product_image_url"):
                    unique.setdefault((normalize(row.get("name")), normalize(row.get("brand"))), row)

        candidates = list(unique.values())
        missing = Product.objects.filter(
            Q(image__isnull=True) | Q(image=""),
            is_archived=False,
            external_image_url="",
        ).distinct()

        supplier_photos = 0
        placeholders = 0
        failures = []

        for product in missing.iterator():
            product_tokens = tokens(product.name)
            brand = normalize(product.brand)
            brand_pool = [row for row in candidates if brand and normalize(row.get("brand")) == brand]
            best = None
            best_score = 0

            for row in brand_pool:
                row_tokens = tokens(row.get("name"))
                overlap = len(product_tokens & row_tokens)
                coverage = overlap / max(1, len(product_tokens))
                precision = overlap / max(1, len(row_tokens))
                score = coverage * 0.72 + precision * 0.28
                if score > best_score:
                    best = row
                    best_score = score

            try:
                if best and best_score >= 0.89:
                    response = requests.get(best["product_image_url"], timeout=30)
                    response.raise_for_status()
                    content_type = response.headers.get("Content-Type", "").lower()
                    if not content_type.startswith("image/"):
                        raise ValueError("supplier URL did not return an image")
                    image_bytes = response.content
                    supplier_photos += 1
                else:
                    image_bytes = branded_placeholder(product)
                    placeholders += 1

                product.image.save(
                    safe_filename(f"product-{product.id}-{product.brand or product.name}"),
                    ContentFile(image_bytes),
                    save=True,
                )
                self.stdout.write(f"#{product.id}: {product.name}")
            except Exception as exc:
                failures.append(f"#{product.id} {product.name}: {exc}")

        self.stdout.write(self.style.SUCCESS(
            f"Supplier photos: {supplier_photos}; branded placeholders: {placeholders}; failures: {len(failures)}"
        ))
        for failure in failures:
            self.stderr.write(failure)
