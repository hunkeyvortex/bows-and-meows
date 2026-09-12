"""Download candidates for local visual QA; never upload or update the database."""
import hashlib
import json
import os
import sys
from io import BytesIO
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "petcare.settings")
import django
django.setup()
from PIL import Image, ImageDraw
from store.management.commands.fix_placeholder_product_images import download_image

out = ROOT / "catalog_exports" / "placeholder_image_review"
out.mkdir(parents=True, exist_ok=True)
manifest = json.loads((ROOT / "product_image_replacement_sources.json").read_text())
results, tiles = {}, []
for pid, candidate in manifest.items():
    if len(sys.argv) > 1 and pid not in sys.argv[1:]:
        continue
    url = candidate.get("replacement_image_url")
    if not url:
        continue
    try:
        data, ext, dimensions = download_image(url)
        (out / f"{pid}.{ext}").write_bytes(data)
        results[pid] = dict(sha256=hashlib.sha256(data).hexdigest(), dimensions=dimensions,
                            path=str(out / f"{pid}.{ext}"))
        image = Image.open(BytesIO(data)).convert("RGBA")
        image.thumbnail((280, 270))
        tile = Image.new("RGB", (300, 310), "white")
        tile.paste(image, ((300-image.width)//2, 28), image)
        ImageDraw.Draw(tile).text((8, 5), f"ID {pid} / {dimensions[0]} x {dimensions[1]}", fill="black")
        tiles.append(tile)
        print(f"{pid}: validated {dimensions}", flush=True)
    except Exception as exc:
        results[pid] = dict(error=type(exc).__name__)
        print(f"{pid}: {type(exc).__name__}", flush=True)
for start in range(0, len(tiles), 12):
    group = tiles[start:start+12]
    sheet = Image.new("RGB", (1200, 310*((len(group)+3)//4)), "#ddd")
    for index, tile in enumerate(group):
        sheet.paste(tile, ((index % 4)*300, (index//4)*310))
    sheet.save(out / f"contact-{start//12}.jpg")
(out / "validation.json").write_text(json.dumps(results, indent=2))
