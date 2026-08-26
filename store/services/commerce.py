from collections import defaultdict
from decimal import Decimal

from django.db.models import Count, Q
from django.utils import timezone

from store.models import BundleItem, OfferCampaign, OrderItem, Product, ProductBundle


def active_campaigns():
    now = timezone.now()
    return OfferCampaign.objects.filter(is_active=True).filter(
        Q(starts_at__isnull=True) | Q(starts_at__lte=now),
        Q(ends_at__isnull=True) | Q(ends_at__gte=now),
    ).select_related("coupon").prefetch_related("products")


def bundle_snapshot(bundle):
    items = list(bundle.items.select_related("product", "variant"))
    regular = Decimal("0.00")
    available = bool(items) and bundle.is_current
    for item in items:
        choice = item.variant or item.product
        regular += choice.price * item.quantity
        if item.product.is_archived or not item.product.is_available or not choice.is_available or choice.stock < item.quantity:
            available = False
    price = bundle.bundle_price
    if price is None:
        discount = Decimal(bundle.discount_percent or 0) / Decimal("100")
        price = (regular * (Decimal("1") - discount)).quantize(Decimal("0.01"))
    price = max(Decimal(price), Decimal("0.00"))
    return {"bundle": bundle, "items": items, "regular_price": regular, "price": price, "saving": max(regular - price, Decimal("0.00")), "available": available}


def bundle_unit_prices(snapshot):
    """Allocate the current bundle total across its items deterministically."""
    regular = snapshot["regular_price"]
    remaining = snapshot["price"]
    allocations = {}
    for index, item in enumerate(snapshot["items"]):
        source_price = item.variant.price if item.variant else item.product.price
        if index == len(snapshot["items"]) - 1:
            allocated_total = remaining
        else:
            allocated_total = (
                snapshot["price"] * (source_price * item.quantity) / regular
            ).quantize(Decimal("0.01")) if regular else Decimal("0.00")
            remaining -= allocated_total
        allocations[(item.product_id, item.variant_id)] = (
            allocated_total / item.quantity
        ).quantize(Decimal("0.01"))
    return allocations


def frequently_bought(product, limit=3):
    valid = Q(order__status__in=("confirmed", "shipped", "delivered")) & ~Q(order__payment_status__in=("failed", "refunded"))
    order_ids = OrderItem.objects.filter(valid, product=product).values("order_id")
    ranked_ids = list(
        OrderItem.objects.filter(valid, order_id__in=order_ids)
        .exclude(product=product)
        .values("product_id")
        .annotate(together=Count("order_id", distinct=True))
        .order_by("-together")
        .values_list("product_id", flat=True)[: limit * 4]
    )
    compatible = Q(pet_type=product.pet_type) | Q(pet_type="both")
    if product.pet_type == "both":
        compatible = Q(pet_type__in=("dog", "cat", "both"))
    products = list(Product.objects.customer_visible().filter(id__in=ranked_ids).filter(compatible))
    products.sort(key=lambda value: ranked_ids.index(value.id))
    if len(products) < limit:
        fallback = Product.objects.customer_visible().filter(compatible).exclude(id__in=[product.id, *[p.id for p in products]])
        fallback = fallback.filter(Q(category=product.category) | Q(is_featured=True)).order_by("-is_featured", "id")
        products.extend(list(fallback[: limit - len(products)]))
    return products[:limit]


def remember_recently_viewed(request, product_id, maximum=10):
    ids = [int(value) for value in request.session.get("recently_viewed", []) if str(value).isdigit()]
    ids = [value for value in ids if value != product_id]
    request.session["recently_viewed"] = [product_id, *ids][:maximum]
    request.session.modified = True


def recently_viewed(request, exclude_id=None, limit=8):
    ids = [int(value) for value in request.session.get("recently_viewed", []) if str(value).isdigit()]
    if exclude_id:
        ids = [value for value in ids if value != exclude_id]
    found = {product.id: product for product in Product.objects.customer_visible().filter(id__in=ids)}
    return [found[value] for value in ids if value in found][:limit]
