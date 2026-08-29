"""Storefront brand-logo registry.

The catalogue remains the source of truth for which brands appear.  This
module only maps normalized catalogue names to approved local static assets;
unknown supplier names deliberately fall back to the template wordmark.
"""

import re


BRAND_LOGO_PATHS = {
    "15furries": "store/images/brands/15-furries-logo.webp",
    "15furriesdropship": "store/images/brands/15-furries-logo.webp",
    "acana": "store/images/brands/acana.png",
    "active": "store/images/brands/active-logo.webp",
    "affinitypetcare": "store/images/brands/affinity-petcare.png",
    "applaws": "store/images/brands/applaws.png",
    "ardengrange": "store/images/brands/arden-grange.png",
    "drools": "store/images/brands/drools.png",
    "erina": "store/images/brands/himalaya.png",
    "erinaep": "store/images/brands/himalaya.png",
    "farmina": "store/images/brands/farmina.png",
    "hills": "store/images/brands/hills.png",
    "himalaya": "store/images/brands/himalaya.png",
    "iams": "store/images/brands/iams.png",
    "kennelkitchen": "store/images/brands/kennel-kitchen-logo.webp",
    "meo": "store/images/brands/me-o-logo.webp",
    "pedigree": "store/images/brands/pedigree.png",
    "purepet": "store/images/brands/purepet-logo.webp",
    "royalcanin": "store/images/brands/royal-canin.png",
    "sheba": "store/images/brands/sheba-logo.webp",
    "whiskas": "store/images/brands/whiskas.png",
    "bowsmeows": "store/images/boww-meow-coral-logo.png",
    "bowwmeow": "store/images/boww-meow-coral-logo.png",
}


def normalize_brand_name(value):
    """Return a stable registry key for supplier-entered brand spelling."""
    return re.sub(r"[^a-z0-9]+", "", (value or "").casefold())


def brand_logo_path(brand_name):
    """Return a local static path, or an empty string for wordmark fallback."""
    return BRAND_LOGO_PATHS.get(normalize_brand_name(brand_name), "")
