"""Isolated tests: no production DB, downloads or Cloudinary calls."""
import csv
import hashlib
import json
from io import BytesIO, StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch, MagicMock

from PIL import Image
from django.core.management import call_command, CommandError
from django.test import TestCase, SimpleTestCase, override_settings

from store.models import Product
from store.management.commands import fix_placeholder_product_images as command


class ScopeTests(SimpleTestCase):
    def test_actual_approved_scope(self):
        rows = command.load_scope(Path(__file__).resolve().parents[1] / "placeholder_product_scope_audit.csv")
        self.assertEqual(len(rows), 64)
        row = next(r for r in rows if r["product_id"] == "39")
        self.assertEqual([v["size"] for v in json.loads(row["variants_sizes"])], ["1.2 KG", "4 KG", "12 KG"])

    def test_altered_scope_rejected(self):
        with TemporaryDirectory() as folder:
            path = Path(folder) / "audit.csv"
            path.write_text("product_id\n99999\n")
            with self.assertRaises(CommandError):
                command.load_scope(path)

    def test_private_source_rejected(self):
        for url in ("http://example.com/x", "file:///tmp/a", "https://user:pass@example.com/x"):
            with self.assertRaises(command.ValidationError):
                command.public_https(url)
        with patch.object(command.socket, "getaddrinfo", return_value=[(2, 1, 6, "", ("127.0.0.1", 443))]):
            with self.assertRaises(command.ValidationError):
                command.public_https("https://example.com/x")

    def download(self, data, mime="image/png", status=200):
        session = MagicMock()
        response = session.__enter__.return_value.get.return_value.__enter__.return_value
        response.status_code = status
        response.headers = {"Content-Type": mime}
        response.iter_content.return_value = [data]
        with patch.object(command.requests, "Session", return_value=session), patch.object(command, "public_https"):
            return command.download_image("https://example.com/pack.png")

    def test_valid_image_decodes(self):
        data = BytesIO()
        Image.new("RGB", (800, 800), "white").save(data, "PNG")
        result = self.download(data.getvalue())
        self.assertEqual(result[2], (800, 800))

    def test_http_and_mime_rejected(self):
        with self.assertRaises(command.ValidationError):
            self.download(b"", status=404)
        with self.assertRaises(command.ValidationError):
            self.download(b"<html>", mime="text/html")

    def test_tiny_and_corrupt_rejected(self):
        data = BytesIO()
        Image.new("RGB", (20, 20)).save(data, "PNG")
        with self.assertRaises(command.ValidationError):
            self.download(data.getvalue())
        with self.assertRaises(Exception):
            self.download(b"not a png")


class ReplacementTests(TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.product = Product.objects.create(name="Exact Adult Pack", brand="Brand", category="dog_food",
                                              price="123.00", stock=12, is_available=True,
                                              image="media/products/product-39-test")
        self.row = dict(product_id=str(self.product.pk), brand=self.product.brand,
                        product_name=self.product.name, category=self.product.category,
                        variants_sizes="[]", current_image=self.product.image.name)
        self.candidate = dict(replacement_source="Manufacturer", source_page="https://example.com/product",
                              replacement_image_url="https://example.com/pack.png", match_verified=True,
                              visual_verified=True, usage_permission="Test fixture permission only",
                              image_sha256=hashlib.sha256(b"image").hexdigest())

    def run_dry(self, candidate=None):
        (self.root / "product_image_replacement_sources.json").write_text(json.dumps(
            {self.row["product_id"]: candidate or self.candidate}))
        with override_settings(BASE_DIR=self.root), patch.object(command, "load_scope", return_value=[self.row]), \
                patch.object(command, "download_image", return_value=(b"image", "png", (800, 800))), \
                patch.object(command, "apply_one") as apply:
            out = StringIO()
            call_command("fix_placeholder_product_images", dry_run=True, stdout=out)
            apply.assert_not_called()
        return out.getvalue()

    def test_dry_run_ready_does_not_write_or_upload(self):
        before = Product.objects.filter(pk=self.product.pk).values().get()
        self.assertIn("READY: 1", self.run_dry())
        self.assertEqual(before, Product.objects.filter(pk=self.product.pk).values().get())
        self.assertFalse((self.root / "product_image_replacement_backup.csv").exists())

    def test_changed_image_skipped(self):
        Product.objects.filter(pk=self.product.pk).update(image="products/new.png")
        self.assertIn("SKIPPED: 1", self.run_dry())

    def test_unverified_permission_manual(self):
        candidate = dict(self.candidate, usage_permission="")
        self.assertIn("MANUAL_REVIEW: 1", self.run_dry(candidate))

    def test_changed_source_bytes_fail(self):
        self.assertIn("FAILED: 1", self.run_dry(dict(self.candidate, image_sha256="wrong")))

    def test_apply_updates_only_image_and_keeps_backup(self):
        before = Product.objects.filter(pk=self.product.pk).values().get()
        backup = self.root / "backup.csv"
        storage = Product._meta.get_field("image").storage
        with patch.object(storage, "save", return_value="products/verified-pack-39.png") as save, \
                patch.object(storage, "delete") as delete:
            command.apply_one(self.row, self.candidate, b"image", "png", backup)
            save.assert_called_once()
            delete.assert_not_called()
            # Reruns cannot overwrite a changed image or upload again.
            with self.assertRaises(command.ValidationError):
                command.apply_one(self.row, self.candidate, b"image", "png", backup)
            save.assert_called_once()
        after = Product.objects.filter(pk=self.product.pk).values().get()
        self.assertEqual({k: v for k, v in before.items() if k != "image"},
                         {k: v for k, v in after.items() if k != "image"})
        with backup.open() as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual(rows[0]["old_image"], before["image"])
        self.assertEqual(rows[-1]["new_cloudinary_image"], after["image"])

    def test_failed_upload_does_not_change_product(self):
        storage = Product._meta.get_field("image").storage
        with patch.object(storage, "save", side_effect=RuntimeError("private failure")):
            with self.assertRaises(RuntimeError):
                command.apply_one(self.row, self.candidate, b"image", "png", self.root / "backup.csv")
        self.product.refresh_from_db()
        self.assertEqual(self.product.image.name, self.row["current_image"])
