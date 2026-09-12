"""Research only: inspect public source pages; never initialize Django or upload."""
import hashlib
import csv
import json
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin

import requests
import truststore
from PIL import Image
from io import BytesIO

truststore.inject_into_ssl()
ROOT = Path(__file__).resolve().parents[1]


class Images(HTMLParser):
    def __init__(self):
        super().__init__()
        self.images = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "img":
            self.images.append({"alt": a.get("alt", ""), "src": a.get("src", ""),
                                "srcset": a.get("srcset", "")})
        if tag == "meta" and a.get("property") == "og:image":
            self.images.insert(0, {"alt": "og:image", "src": a.get("content", "")})


if __name__ == "__main__":
    manifest = json.loads((ROOT / "product_image_replacement_sources.json").read_text())
    with (ROOT / "placeholder_product_scope_audit.csv").open(encoding="utf-8-sig") as handle:
        audited = {r["product_id"]: r for r in csv.DictReader(handle)}
    for pid in sys.argv[1:]:
        page = manifest[pid]["source_page"]
        try:
            if "supertails.com/products/" in page:
                r = requests.get(page.split("?")[0] + ".js", timeout=25)
                product = r.json()
                sizes = {v["size"].lower().replace(" ", "") for v in json.loads(audited[pid]["variants_sizes"])}
                variants = []
                for v in product.get("variants", []):
                    if v["title"].lower().replace(" ", "") in sizes:
                        image = v.get("featured_image") or {}
                        variants.append({"title": v["title"], "src": image.get("src"),
                                         "alt": image.get("alt"), "width": image.get("width")})
                print(json.dumps({"id": pid, "http": r.status_code,
                                  "title": product.get("title"),
                                  "variants": variants[:2]}), flush=True)
                continue
            r = requests.get(page, timeout=25)
            parser = Images()
            parser.feed(r.text)
            images = [{"alt": i["alt"], "src": urljoin(page, i["src"])} for i in parser.images
                      if i["src"] and not any(s in i["src"].lower() for s in
                      ("logo", "100x100", "width=100", "flag", "icon", "placeholder", "header", "footer"))]
            unique = list({i["src"]: i for i in images}.values())
            if "royalcanin.com" in page:
                unique = [i for i in unique if "petcare.global" in i["src"] or "packshot" in i["src"]][:1]
            print(json.dumps({"id": pid, "http": r.status_code, "images": unique[-18:]}), flush=True)
        except Exception as exc:
            print(json.dumps({"id": pid, "error": type(exc).__name__}))
