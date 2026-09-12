"""Replace only the 64 reviewed placeholders; use a human-reviewed source manifest.

No fuzzy matching, global catalogue scan, model save hooks, or asset deletion.
Dry-run reads the database and downloads candidates into memory only.
"""
import csv
import hashlib
import ipaddress
import json
import os
import socket
import warnings
from collections import Counter
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from urllib.parse import urlsplit, urljoin
from uuid import uuid4

import requests
from PIL import Image
from django.conf import settings
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction

from store.models import Product

AUDIT_SHA256 = "bc837015659dac26f696ae92c06fc596a967350df7351f194a5db2bb5207537e"
PREFIX = "media/products/product-"
REPORT_FIELDS = ["product_id", "brand", "product_name", "old_image",
                 "replacement_source", "source_page", "replacement_image_url",
                 "new_cloudinary_image", "status", "confidence", "notes"]
BACKUP_FIELDS = ["product_id", "brand", "product_name", "old_image",
                 "old_external_image_url", "replacement_source", "source_page",
                 "replacement_image_url", "new_cloudinary_image", "timestamp"]
MAX_BYTES = 15 * 1024 * 1024


class ValidationError(Exception):
    """Only fixed, non-secret messages may be included in reports."""


def load_scope(path):
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != AUDIT_SHA256:
        raise CommandError("Audit checksum mismatch. Refusing a changed or expanded scope.")
    rows = list(csv.DictReader(raw.decode("utf-8-sig").splitlines()))
    ids = [int(row["product_id"]) for row in rows]
    if len(ids) != 64 or len(set(ids)) != 64:
        raise CommandError("The audited scope must contain exactly 64 unique product IDs.")
    if any(not row["current_image"].startswith(PREFIX) for row in rows):
        raise CommandError("Audit contains an unexpected original image.")
    return rows


def public_https(url):
    parsed = urlsplit(url)
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username
            or parsed.password or parsed.port not in (None, 443)):
        raise ValidationError("Only public HTTPS sources without credentials are allowed")
    # Validate every redirect as well; internal metadata/loopback addresses prohibited.
    addresses = socket.getaddrinfo(parsed.hostname, 443, type=socket.SOCK_STREAM)
    if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):
        raise ValidationError("Non-public source address rejected")


def download_image(url):
    with requests.Session() as session:
        session.trust_env = False  # Never forward environment proxy credentials.
        for _ in range(5):
            public_https(url)
            with session.get(url, timeout=(10, 30), stream=True, allow_redirects=False) as response:
                if response.status_code in (301, 302, 303, 307, 308):
                    url = urljoin(url, response.headers.get("Location", ""))
                    continue
                if response.status_code != 200:
                    raise ValidationError(f"Image HTTP status {response.status_code}")
                mime = response.headers.get("Content-Type", "").split(";")[0].lower()
                if mime not in ("image/jpeg", "image/png", "image/webp"):
                    raise ValidationError("Unsupported or non-image Content-Type")
                chunks, length = [], 0
                for chunk in response.iter_content(65536):
                    length += len(chunk)
                    if length > MAX_BYTES:
                        raise ValidationError("Image exceeds 15 MiB limit")
                    chunks.append(chunk)
                data = b"".join(chunks)
                break
        else:
            raise ValidationError("Too many image redirects")
    with warnings.catch_warnings():
        warnings.simplefilter("error", Image.DecompressionBombWarning)
        with Image.open(BytesIO(data)) as image:
            fmt, dimensions = image.format, image.size
            if fmt not in ("JPEG", "PNG", "WEBP"):
                raise ValidationError("Unsupported decoded image format")
            if mime != {"JPEG": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp"}[fmt]:
                raise ValidationError("Content-Type and decoded format disagree")
            if min(dimensions) < 400 or max(dimensions) < 600:
                raise ValidationError("Image too small (requires shortest side 400px, longest 600px; prefers 800px)")
            if image.width * image.height > 25000000 or getattr(image, "n_frames", 1) != 1:
                raise ValidationError("Oversized or animated image rejected")
            image.verify()
        with Image.open(BytesIO(data)) as image:
            image.load()
    return data, {"JPEG": "jpg", "PNG": "png", "WEBP": "webp"}[fmt], dimensions


def scope_matches(product, row):
    return (product is not None and product.is_available and not product.is_archived
            and product.image.name == row["current_image"]
            and product.name == row["product_name"] and product.brand == row["brand"]
            and product.category == row["category"]
            and sorted((v.pk, v.size) for v in product.variants.all()) == sorted(
                (v["variant_id"], v["size"]) for v in json.loads(row["variants_sizes"])))


def append_backup(path, row):
    # Append+fsync BEFORE upload, then append completion with the stored asset name.
    # Previous backups are never truncated. Blank new name denotes an intent record.
    if path.exists() and path.stat().st_size:
        with path.open(encoding="utf-8-sig", newline="") as handle:
            if next(csv.reader(handle), []) != BACKUP_FIELDS:
                raise ValidationError("Existing backup schema differs; refusing to overwrite")
    has_header = path.exists() and path.stat().st_size > 0
    with path.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=BACKUP_FIELDS)
        if not has_header:
            writer.writeheader()
        writer.writerow(row)
        handle.flush()
        os.fsync(handle.fileno())


def apply_one(row, candidate, data, ext, backup):
    with transaction.atomic():
        product = Product.objects.select_for_update().filter(pk=int(row["product_id"])).first()
        if not scope_matches(product, row):
            raise ValidationError("Audited product changed before upload; skipped")
        entry = {key: "" for key in BACKUP_FIELDS}
        entry.update(product_id=product.pk, brand=product.brand, product_name=product.name,
                     old_image=product.image.name, old_external_image_url=product.external_image_url,
                     replacement_source=candidate["replacement_source"],
                     source_page=candidate["source_page"],
                     replacement_image_url=candidate["replacement_image_url"],
                     timestamp=datetime.now(timezone.utc).isoformat())
        append_backup(backup, entry)
        # Use the field's existing storage; unique path cannot overwrite an old asset.
        storage = product.image.storage
        name = storage.save(f"products/verified-pack-{product.pk}-{uuid4().hex}.{ext}", ContentFile(data))
        entry["new_cloudinary_image"] = name
        append_backup(backup, entry)  # Persist rollback information before DB write.
        changed = Product.objects.filter(pk=product.pk, image=row["current_image"],
                                         is_available=True, is_archived=False).update(image=name)
        if changed != 1:
            raise ValidationError("Concurrent product edit prevented update; uploaded asset retained")
        return name


class Command(BaseCommand):
    help = "Preview or replace the exact 64 audited placeholders using reviewed image sources."
    requires_system_checks = []

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        root = Path(settings.BASE_DIR)
        scope = load_scope(root / "placeholder_product_scope_audit.csv")
        manifest = json.loads((root / "product_image_replacement_sources.json").read_text(encoding="utf-8"))
        if set(manifest) != {row["product_id"] for row in scope}:
            raise CommandError("Source manifest must contain exactly the audited IDs.")
        dry_run = options["dry_run"]
        backup = root / "product_image_replacement_backup.csv"
        # Separate dry-run artifact: READY is not a final replacement status.
        report = root / ("product_image_replacement_dry_run.csv" if dry_run
                         else "product_image_replacement_report.csv")
        if not dry_run and "cloudinary" not in settings.STORAGES["default"]["BACKEND"].lower():
            raise CommandError("Real replacements require the existing Cloudinary storage backend.")
        try:
            with transaction.atomic():
                if connection.vendor == "postgresql":
                    with connection.cursor() as cursor:
                        cursor.execute("SET TRANSACTION READ ONLY")
                products = {p.pk: p for p in Product.objects.filter(
                    pk__in=[int(row["product_id"]) for row in scope]).prefetch_related("variants")}
                # Evaluate variant queries within the read-only transaction.
                matches = {row["product_id"]: scope_matches(products.get(int(row["product_id"])), row)
                           for row in scope}
        except Exception as exc:
            raise CommandError(f"Database audit failed ({type(exc).__name__}); details suppressed") from None
        counts = Counter()
        final_rows = []
        if report.exists():
            report.rename(report.with_name(f"{report.stem}-{uuid4().hex}{report.suffix}"))
        with report.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=REPORT_FIELDS)
            writer.writeheader()
            for row in scope:
                candidate = manifest[row["product_id"]]
                result = {key: "" for key in REPORT_FIELDS}
                result.update(product_id=row["product_id"], brand=row["brand"],
                              product_name=row["product_name"], old_image=row["current_image"],
                              status="MANUAL_REVIEW", confidence=candidate.get("confidence", "unverified"),
                              notes=candidate.get("notes", "Exact image not verified"))
                for key in ("replacement_source", "source_page", "replacement_image_url"):
                    result[key] = candidate.get(key, "")
                try:
                    if not matches[row["product_id"]]:
                        result.update(status="SKIPPED", notes="Current record/variants differ from audited scope")
                    elif candidate.get("match_verified") and candidate.get("visual_verified"):
                        data, ext, dimensions = download_image(candidate["replacement_image_url"])
                        digest = hashlib.sha256(data).hexdigest()
                        if digest != candidate.get("image_sha256"):
                            raise ValidationError("Source bytes differ from visually reviewed image")
                        if not candidate.get("usage_permission"):
                            result["notes"] += "; Image validated but commercial reuse permission not confirmed"
                        elif dry_run:
                            result.update(status="READY", notes=f"Exact reviewed pack; validated {dimensions}; no upload or DB write")
                        else:
                            result["new_cloudinary_image"] = apply_one(row, candidate, data, ext, backup)
                            result.update(status="REPLACED", notes="Only Product.image updated; original asset retained")
                except Exception as exc:
                    reason = str(exc) if isinstance(exc, ValidationError) else type(exc).__name__
                    result.update(status="FAILED", notes=f"Validation/replacement failed: {reason}")
                counts[result["status"]] += 1
                writer.writerow(result)
                final = dict(result)
                if dry_run and final["status"] == "READY":
                    final.update(status="SKIPPED", notes="Dry-run READY; not applied; awaiting user approval")
                final_rows.append(final)
                handle.flush()
                self.stdout.write(f"Product {row['product_id']}: {row['product_name']}\n"
                                  f"Sizes: {', '.join(v['size'] for v in json.loads(row['variants_sizes']))}\n"
                                  f"OLD: {row['current_image']}\nSOURCE: {result['source_page']}\n"
                                  f"REPLACEMENT: {result['replacement_image_url']}\n"
                                  f"STATUS: {result['status']} | {result['notes']}\n")
        self.stdout.write(f"Total targets: {len(scope)}; " + "; ".join(
            f"{key}: {counts[key]}" for key in ("READY", "MANUAL_REVIEW", "FAILED", "SKIPPED", "REPLACED")))
        self.stdout.write(f"Report: {report.name}")
        if dry_run:
            final_report = root / "product_image_replacement_report.csv"
            if final_report.exists():
                final_report.rename(final_report.with_name(f"{final_report.stem}-{uuid4().hex}.csv"))
            with final_report.open("x", encoding="utf-8-sig", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=REPORT_FIELDS)
                writer.writeheader()
                writer.writerows(final_rows)
