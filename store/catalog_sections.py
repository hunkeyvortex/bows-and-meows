"""Shared inventory/storefront grouping and reversible launch exclusions."""
from django.db.models import Q

SECTION_CHOICES = (("dry", "Dry Food"), ("wet", "Wet Food"),
                   ("treats", "Treats"), ("wellness", "Wellness"))


def paused_catalog_query():
    garments = r"(^|[^a-z])(shirts?|t-shirts?|tshirts?|bandanas?|hoodies?|sweaters?|jackets?|raincoats?|costumes?|dresses|dress|kurta|sherwani|lehenga|clothing|apparel)([^a-z]|$)"
    return (Q(product_type__in=("medicine", "vaccine")) |
            Q(requires_prescription=True) |
            Q(category__in=("medicine", "parasite_control", "respiratory_care",
                            "kidney_care", "heart_care", "dog_health",
                            "cat_health", "bird_health", "exotic_health")) |
            Q(name__iregex=garments))


def filter_section(products, section):
    food = Q(product_type="food") | Q(category__in=("dog_food", "cat_food", "bird_food"))
    wet = Q(name__iregex=r"(^|[^a-z])(wet|gravy|pouch|pate|jelly|canned|mousse)([^a-z]|$)")
    dry = Q(name__iregex=r"(^|[^a-z])(dry|kibble)([^a-z]|$)")
    if section == "dry":
        return products.filter(food & dry).exclude(wet)
    if section == "wet":
        return products.filter(food & wet)
    if section == "treats":
        return products.filter(Q(product_type="treat") | Q(category__in=("dog_treat", "cat_treat", "treat")))
    if section == "wellness":
        return products.filter(product_type="supplement")
    return products
