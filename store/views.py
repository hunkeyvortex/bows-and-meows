from django.shortcuts import render, redirect, get_object_or_404
from .models import Product, ProductVariant, Order, OrderItem
from django.contrib.auth.models import User
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.views.decorators.http import require_POST
from django.utils.http import url_has_allowed_host_and_scheme
from .models import Product, Order, OrderItem, Pet
from django.contrib.auth.models import User
from django.db.models import Sum
from django.db.models import Sum, Count
from django.db.models import Sum, Count, F, DecimalField, ExpressionWrapper, OuterRef, Subquery
from django.db.models.functions import Coalesce, Lower, Trim, TruncDate
from datetime import timedelta
from django.utils import timezone
from django.db.models import Avg
from .models import Product, Order, OrderItem, Pet, Review
from .models import Product, Order, OrderItem, Pet, Review, Wishlist
from .models import Address
from django.db.models import Sum, Q, Case, When, Value, IntegerField
from .models import ProductImage
import razorpay
import os
import requests
import uuid
import mimetypes

from urllib.parse import urlparse
from django.core.files.base import ContentFile
import csv
import io
from brevo import Brevo
from brevo.transactional_emails import (
    SendTransacEmailRequestSender,
    SendTransacEmailRequestToItem,
)
from brevo.core.api_error import ApiError
import re
from django.db import transaction
import uuid
from decimal import Decimal, InvalidOperation
from PIL import Image as PillowImage, UnidentifiedImageError
from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.core.mail import EmailMultiAlternatives
from django.core.paginator import Paginator
from brevo.core.api_error import ApiError
from .models import (
    Product,
    ProductVariant,
    FeedingGuide,
    Order,
    OrderItem,
    Coupon,
)
def home(request):

    base_products = (
        Product.objects
        .filter(
            is_available=True,
            is_archived=False,
            stock__gt=0
        )
        .prefetch_related("variants")
        .annotate(
            sold_count=Sum(
                "orderitem__quantity",
                filter=Q(
                    orderitem__order__status__in=[
                        "confirmed",
                        "shipped",
                        "delivered",
                    ]
                )
            )
        )
    )


    # ==========================================
    # BEST SELLERS
    # ==========================================

    best_sellers = (
        base_products
        .order_by(
            "-sold_count",
            "-is_featured",
            "-id"
        )[:6]
    )


    # ==========================================
    # POPULAR DOG PRODUCTS
    # ==========================================

    dog_product_match = (
        Q(category__startswith="dog_")
        | (Q(pet_type="dog") & ~Q(category__startswith="cat_"))
    )
    cat_product_match = (
        Q(category__startswith="cat_")
        | (Q(pet_type="cat") & ~Q(category__startswith="dog_"))
    )

    popular_dogs = (
        base_products
        .filter(dog_product_match)
        .order_by(
            "-sold_count",
            "-is_featured",
            "-id"
        )[:8]
    )


    # ==========================================
    # POPULAR CAT PRODUCTS
    # ==========================================

    popular_cats = (
        base_products
        .filter(cat_product_match)
        .order_by(
            "-sold_count",
            "-is_featured",
            "-id"
        )[:8]
    )

    # Keep the lower "Popular Right Now" grid evenly balanced. Alternating
    # species also prevents one group from occupying an entire mobile row.
    top_five_dogs = list(popular_dogs[:5])
    top_five_cats = list(popular_cats[:5])
    popular_picks = []
    for index in range(5):
        if index < len(top_five_dogs):
            popular_picks.append(top_five_dogs[index])
        if index < len(top_five_cats):
            popular_picks.append(top_five_cats[index])

    # Imported catalogue categories are not always reliable. For this section,
    # require food language in the product name and rank recognised best-selling
    # formulas first. The shop's completed sales break ties within that ranking.
    food_name_terms = (
        "food", "kibble", "meal", "gravy", "jelly", "chunks",
        "dry", "wet", "baked", "nutrition",
    )
    non_food_terms = (
        "shirt", "t-shirt", "jacket", "dress", "hoodie", "sweater",
        "collar", "leash", "harness", "bed", "toy", "bowl", "mat",
        "shampoo", "tablet", "syrup", "drop", "powder", "lotion",
        "wipe", "pad", "paste",
    )

    dog_priority_terms = (
        "Pedigree Chicken and Vegetables Adult",
        "Royal Canin Mini Puppy",
        "Royal Canin Maxi Adult",
        "Drools Optimum Performance Adult",
        "Farmina N&D Pumpkin Lamb",
        "Purina Pro Plan Chicken Large Breed Adult",
        "Henlo Baked Chicken",
        "Royal Canin Maxi Puppy",
        "Pedigree Chicken and Milk Puppy",
        "Pedigree Meat and Rice Adult",
    )
    cat_priority_terms = (
        "Royal Canin Persian Adult",
        "Whiskas Ocean Fish Adult",
        "Me-O Persian Adult",
        "Purepet Adult Ocean Fish",
        "Royal Canin Kitten",
        "Farmina N&D Prime Chicken Adult Cat",
        "Whiskas Ocean Fish Kitten",
        "Whiskas Tuna in Jelly",
        "Whiskas Chicken in Gravy",
        "Me-O Seafood Adult",
    )

    def ranked_food_products(pet, category, priority_terms):
        food_words = Q()
        for term in food_name_terms:
            food_words |= Q(name__icontains=term)

        excluded_words = Q()
        for term in non_food_terms:
            excluded_words |= Q(name__icontains=term)

        pet_match = (
            Q(pet_type=pet)
            | Q(category=category)
            | Q(name__icontains=pet)
            | Q(name__icontains="puppy" if pet == "dog" else "kitten")
        )

        priority_cases = [
            When(name__icontains=term, then=Value(index))
            for index, term in enumerate(priority_terms)
        ]

        return (
            base_products
            .filter(pet_match & food_words)
            .exclude(excluded_words)
            .annotate(
                market_rank=Case(
                    *priority_cases,
                    default=Value(100),
                    output_field=IntegerField(),
                )
            )
            .order_by("market_rank", "-sold_count", "-is_featured", "-id")[:10]
        )

    top_dog_foods = ranked_food_products("dog", "dog_food", dog_priority_terms)
    top_cat_foods = ranked_food_products("cat", "cat_food", cat_priority_terms)

    famous_brands = list(
        Product.objects
        .filter(is_available=True, is_archived=False, stock__gt=0)
        .exclude(brand__isnull=True)
        .exclude(brand="")
        .values("brand")
        .annotate(
            product_count=Count("id", distinct=True),
            brand_sales=Sum(
                "orderitem__quantity",
                filter=Q(
                    orderitem__order__status__in=[
                        "confirmed",
                        "shipped",
                        "delivered",
                    ]
                ),
            ),
        )
        .order_by("-brand_sales", "-product_count", "brand")[:12]
    )

    offers = (
        base_products
        .filter(original_price__isnull=False, original_price__gt=F("price"))
        .order_by("price", "-is_featured", "-id")[:8]
    )


    # Keep this for your existing lower product section
    products = (
        base_products
        .order_by(
            "-is_featured",
            "-id"
        )
    )


    context = {

        "products":
            products,

        "best_sellers":
            best_sellers,

        "popular_dogs":
            popular_dogs,

        "popular_cats":
            popular_cats,

        "popular_picks":
            popular_picks,

        "top_dog_foods":
            top_dog_foods,

        "top_cat_foods":
            top_cat_foods,

        "famous_brands":
            famous_brands,

        "offers":
            offers,
    }


    return render(
        request,
        "store/home.html",
        context
    )
def send_brevo_email(to_email, to_name, subject, html_content):

    api_key = os.getenv("BREVO_API_KEY")
    sender_email = os.getenv("BREVO_SENDER_EMAIL")
    sender_name = os.getenv("BREVO_SENDER_NAME", "Boww & Meow")

    if not api_key:
        print("BREVO ERROR: BREVO_API_KEY missing")
        return

    if not sender_email:
        print("BREVO ERROR: BREVO_SENDER_EMAIL missing")
        return

    if not to_email:
        print("BREVO ERROR: recipient email missing")
        return

    try:
        client = Brevo(api_key=api_key)

        result = client.transactional_emails.send_transac_email(
            subject=subject,
            html_content=html_content,

            sender=SendTransacEmailRequestSender(
                name=sender_name,
                email=sender_email,
            ),

            to=[
                SendTransacEmailRequestToItem(
                    email=to_email,
                    name=to_name or "",
                )
            ],
        )

        print(
            "BREVO EMAIL SENT:",
            result.message_id
        )

    except ApiError as e:
        print(
            "BREVO API ERROR:",
            e.status_code,
            e.body
        )

    except Exception as e:
        print(
            "BREVO UNKNOWN ERROR:",
            str(e)
        )

def _sync_product_stock(product):
    variants = product.variants.all()
    if variants.exists():
        total_stock = sum(v.stock for v in variants)
        product.stock = total_stock
        product.is_available = total_stock > 0
        product.save(update_fields=["stock", "is_available"])


def _reserve_order_inventory(order):
    """Deduct an order's stock once, using row locks."""
    with transaction.atomic():
        locked_order = Order.objects.select_for_update().get(id=order.id)
        if locked_order.inventory_reserved:
            return locked_order

        affected = set()
        for item in locked_order.items.select_related("product", "variant"):
            if item.variant_id:
                variant = ProductVariant.objects.select_for_update().get(id=item.variant_id)
                if not variant.is_available or item.quantity > variant.stock:
                    raise ValueError(
                        f"Not enough stock for {item.product.name} {item.variant_size}"
                    )
                variant.stock -= item.quantity
                variant.is_available = variant.stock > 0
                variant.save(update_fields=["stock", "is_available"])
                affected.add(item.product_id)
            else:
                product = Product.objects.select_for_update().get(id=item.product_id)
                if not product.is_available or item.quantity > product.stock:
                    raise ValueError(f"Not enough stock for {product.name}")
                product.stock -= item.quantity
                product.is_available = product.stock > 0
                product.save(update_fields=["stock", "is_available"])

        for product_id in affected:
            _sync_product_stock(Product.objects.get(id=product_id))

        locked_order.inventory_reserved = True
        locked_order.save(update_fields=["inventory_reserved"])
        return locked_order


def _restore_order_inventory(order):
    """Return reserved quantities once. Safe to call repeatedly."""
    with transaction.atomic():
        locked_order = Order.objects.select_for_update().get(id=order.id)
        if not locked_order.inventory_reserved:
            return locked_order

        affected = set()
        for item in locked_order.items.select_related("product", "variant"):
            if item.variant_id:
                variant = ProductVariant.objects.select_for_update().filter(id=item.variant_id).first()
                if variant:
                    variant.stock += item.quantity
                    variant.is_available = True
                    variant.save(update_fields=["stock", "is_available"])
                    affected.add(item.product_id)
            else:
                product = Product.objects.select_for_update().get(id=item.product_id)
                product.stock += item.quantity
                product.is_available = True
                product.save(update_fields=["stock", "is_available"])

        for product_id in affected:
            _sync_product_stock(Product.objects.get(id=product_id))

        locked_order.inventory_reserved = False
        locked_order.save(update_fields=["inventory_reserved"])
        return locked_order


def _request_can_access_order(request, order):
    return (
        request.user.is_authenticated
        and order.user_id == request.user.id
    ) or order.id in request.session.get("order_access_ids", [])


def _cart_line_key(product_id, variant_id=None):
    return f"p{product_id}:v{variant_id}" if variant_id else f"p{product_id}"


def _normalize_cart(request):
    raw_cart = request.session.get("cart", {})
    if not isinstance(raw_cart, dict):
        raw_cart = {}
    normalized = {}
    for raw_key, raw_value in raw_cart.items():
        if isinstance(raw_value, dict):
            try:
                product_id = int(raw_value.get("product_id"))
                quantity = max(int(raw_value.get("quantity", 1)), 1)
            except (TypeError, ValueError):
                continue
            variant_id = raw_value.get("variant_id")
            try:
                variant_id = int(variant_id) if variant_id not in ("", None) else None
            except (TypeError, ValueError):
                variant_id = None
        else:
            try:
                product_id = int(raw_key)
                quantity = max(int(raw_value), 1)
            except (TypeError, ValueError):
                continue
            variant_id = None
        key = _cart_line_key(product_id, variant_id)
        normalized[key] = {
            "product_id": product_id,
            "variant_id": variant_id,
            "quantity": quantity,
        }
    request.session["cart"] = normalized
    request.session.modified = True
    return normalized


def _pack_size_in_base_units(size):
    if not size:
        return None
    match = re.search(r"(\d+(?:\.\d+)?)\s*(kg|g|ml|l)\b", size.strip().lower())
    if not match:
        return None
    try:
        amount = Decimal(match.group(1))
    except InvalidOperation:
        return None
    unit = match.group(2)
    if unit == "kg":
        return "weight", amount * Decimal("1000")
    if unit == "g":
        return "weight", amount
    if unit == "l":
        return "volume", amount * Decimal("1000")
    if unit == "ml":
        return "volume", amount
    return None


def _format_extra_pack_amount(kind, amount):
    amount = Decimal(amount)
    if kind == "weight":
        return f"{(amount / Decimal('1000')).normalize()} KG" if amount >= 1000 else f"{amount.normalize()} g"
    if kind == "volume":
        return f"{(amount / Decimal('1000')).normalize()} L" if amount >= 1000 else f"{amount.normalize()} ml"
    return str(amount)


def _find_pack_upgrade(product, current_variant, quantity):
    if not current_variant:
        return None
    current_pack = _pack_size_in_base_units(current_variant.size)
    if not current_pack:
        return None
    kind, current_units = current_pack
    current_total_units = current_units * Decimal(quantity)
    current_total_cost = current_variant.price * Decimal(quantity)
    if current_total_units <= 0:
        return None
    current_unit_cost = current_total_cost / current_total_units
    best = None

    for candidate in product.variants.filter(is_available=True, stock__gt=0).exclude(id=current_variant.id):
        candidate_pack = _pack_size_in_base_units(candidate.size)
        if not candidate_pack:
            continue
        candidate_kind, candidate_units = candidate_pack
        if candidate_kind != kind or candidate_units <= current_total_units:
            continue
        candidate_unit_cost = candidate.price / candidate_units
        if candidate_unit_cost >= current_unit_cost:
            continue
        extra_cost = candidate.price - current_total_cost
        if extra_cost <= 0:
            continue
        extra_units = candidate_units - current_total_units
        saving_percent = ((current_unit_cost - candidate_unit_cost) / current_unit_cost * Decimal("100"))
        suggestion = {
            "variant": candidate,
            "extra_cost": extra_cost,
            "extra_size_text": _format_extra_pack_amount(kind, extra_units),
            "unit_saving_percent": int(saving_percent.quantize(Decimal("1"))),
        }
        if best is None or extra_cost < best["extra_cost"]:
            best = suggestion
    return best


def _build_cart_items(request):
    cart = _normalize_cart(request)
    cart_items = []
    total = Decimal("0.00")
    invalid = []
    for line_key, entry in cart.items():
        product = Product.objects.filter(id=entry["product_id"]).first()
        if not product or product.is_archived or not product.is_available:
            invalid.append(line_key)
            continue
        variant = None
        if entry.get("variant_id"):
            variant = ProductVariant.objects.filter(id=entry["variant_id"], product=product).first()
            if not variant:
                invalid.append(line_key)
                continue
        quantity = max(int(entry.get("quantity", 1)), 1)
        unit_price = variant.price if variant else product.price
        subtotal = unit_price * quantity
        total += subtotal
        cart_items.append({
            "cart_key": line_key,
            "product": product,
            "variant": variant,
            "quantity": quantity,
            "unit_price": unit_price,
            "available_stock": variant.stock if variant else product.stock,
            "subtotal": subtotal,
            "upgrade_suggestion": _find_pack_upgrade(product, variant, quantity) if variant else None,
        })
    for key in invalid:
        cart.pop(key, None)
    if invalid:
        request.session["cart"] = cart
        request.session.modified = True
    return cart_items, total


def _cart_pricing(request, subtotal):
    pricing = {
        "subtotal": subtotal,
        "discount": Decimal("0.00"),
        "total": subtotal,
        "coupon": None,
        "coupon_error": "",
    }
    code = str(request.session.get("coupon_code", "")).strip().upper()
    if not code:
        return pricing
    coupon = Coupon.objects.filter(code__iexact=code).first()
    if not coupon:
        request.session.pop("coupon_code", None)
        pricing["coupon_error"] = "That coupon no longer exists."
        return pricing
    error = coupon.validation_error(subtotal)
    if error:
        # Do not keep an expired, exhausted or otherwise invalid coupon
        # attached to the checkout session. Minimum-spend coupons can remain
        # so they become valid if the customer adds more products.
        if not error.startswith("Spend at least"):
            request.session.pop("coupon_code", None)
            request.session.modified = True
        pricing["coupon_error"] = error
        return pricing
    discount = coupon.discount_for(subtotal)
    pricing.update({"coupon": coupon, "discount": discount, "total": subtotal - discount})
    return pricing


def _available_coupons(subtotal):
    """Return currently usable offers, putting coupons eligible now first."""
    offers = []
    for coupon in Coupon.objects.filter(is_active=True).order_by("minimum_order", "-discount_percent"):
        error = coupon.validation_error(subtotal)
        # Keep minimum-spend offers visible so customers know how to unlock them;
        # hide expired, future and exhausted promotions.
        if error and not error.startswith("Spend at least"):
            continue
        offers.append({"coupon": coupon, "eligible": not error, "message": error})
    return offers[:6]


@require_POST
def add_to_cart(request, product_id):
    product = get_object_or_404(Product, id=product_id, is_available=True, is_archived=False)
    if product.requires_prescription:
        messages.warning(
            request,
            "This veterinary medicine requires a valid prescription. Please contact us before ordering.",
        )
        return redirect("product_detail", product_id=product.id)
    cart = _normalize_cart(request)
    variant_id = request.GET.get("variant") or request.POST.get("variant")
    variant = None

    if variant_id:
        variant = get_object_or_404(ProductVariant, id=variant_id, product=product)
        if not variant.is_available or variant.stock <= 0:
            return redirect("product_detail", product_id=product.id)
    elif product.variants.exists():
        return redirect("product_detail", product_id=product.id)

    line_key = _cart_line_key(product.id, variant.id if variant else None)
    available_stock = variant.stock if variant else product.stock
    current = cart.get(line_key, {}).get("quantity", 0)

    if current < available_stock:
        cart[line_key] = {
            "product_id": product.id,
            "variant_id": variant.id if variant else None,
            "quantity": current + 1,
        }

    replace_key = request.POST.get("replace") or request.GET.get("replace")
    if replace_key and replace_key != line_key and replace_key in cart:
        del cart[replace_key]

    request.session["cart"] = cart
    request.session.modified = True
    return redirect("cart")


@require_POST
def buy_now(request, product_id):
    """Start a focused checkout containing only the selected product/variant."""
    product = get_object_or_404(
        Product,
        id=product_id,
        is_available=True,
        is_archived=False,
    )
    if product.requires_prescription:
        messages.warning(
            request,
            "This veterinary medicine requires a valid prescription. Please contact us before ordering.",
        )
        return redirect("product_detail", product_id=product.id)

    variant_id = request.POST.get("variant")
    variant = None
    if variant_id:
        variant = get_object_or_404(ProductVariant, id=variant_id, product=product)
        if not variant.is_available or variant.stock <= 0:
            messages.error(request, "That package size is currently unavailable.")
            return redirect("product_detail", product_id=product.id)
    elif product.variants.exists():
        messages.error(request, "Please choose a package size before buying.")
        return redirect("product_detail", product_id=product.id)
    elif product.stock <= 0:
        return redirect("product_detail", product_id=product.id)

    line_key = _cart_line_key(product.id, variant.id if variant else None)
    request.session["cart"] = {
        line_key: {
            "product_id": product.id,
            "variant_id": variant.id if variant else None,
            "quantity": 1,
        }
    }
    request.session.pop("coupon_code", None)
    request.session.modified = True
    return redirect("checkout")


def cart(request):
    cart_items, subtotal = _build_cart_items(request)
    pricing = _cart_pricing(request, subtotal)
    return render(request, "store/cart.html", {
        "cart_items": cart_items,
        "available_coupons": _available_coupons(subtotal),
        **pricing,
    })


@require_POST
def apply_coupon(request):
    code = request.POST.get("coupon_code", "").strip().upper()
    if request.POST.get("remove"):
        request.session.pop("coupon_code", None)
        messages.success(request, "Coupon removed.")
        return redirect(request.POST.get("next") or "cart")
    _, subtotal = _build_cart_items(request)
    coupon = Coupon.objects.filter(code__iexact=code).first()
    error = "Please enter a valid coupon code." if not coupon else coupon.validation_error(subtotal)
    if error:
        messages.error(request, error)
    else:
        request.session["coupon_code"] = coupon.code
        request.session.modified = True
        messages.success(request, f"{coupon.code} applied — you save {coupon.discount_percent}%.")
    return redirect(request.POST.get("next") or "cart")


@require_POST
def remove_from_cart(request, product_id):
    cart = _normalize_cart(request)
    variant_id = request.POST.get("variant") or request.GET.get("variant")
    cart.pop(_cart_line_key(product_id, variant_id), None)
    request.session["cart"] = cart
    request.session.modified = True
    return redirect("cart")


@require_POST
def increase_quantity(request, product_id):
    cart = _normalize_cart(request)
    variant_id = request.POST.get("variant") or request.GET.get("variant")
    line_key = _cart_line_key(product_id, variant_id)
    entry = cart.get(line_key)
    if not entry:
        return redirect("cart")

    product = get_object_or_404(Product, id=product_id)
    variant = get_object_or_404(ProductVariant, id=variant_id, product=product) if variant_id else None
    max_stock = variant.stock if variant else product.stock
    if entry["quantity"] < max_stock:
        entry["quantity"] += 1
    cart[line_key] = entry
    request.session["cart"] = cart
    request.session.modified = True
    return redirect("cart")


@require_POST
def decrease_quantity(request, product_id):
    cart = _normalize_cart(request)
    variant_id = request.POST.get("variant") or request.GET.get("variant")
    line_key = _cart_line_key(product_id, variant_id)
    entry = cart.get(line_key)
    if entry:
        entry["quantity"] -= 1
        if entry["quantity"] <= 0:
            cart.pop(line_key, None)
        else:
            cart[line_key] = entry
    request.session["cart"] = cart
    request.session.modified = True
    return redirect("cart")

def send_order_confirmation(order):

    if not order.email:
        return

    subject = (
        f"Boww & Meow - Order #{order.id} Confirmed"
    )

    html_content = render_to_string(
        "store/emails/order_confirmation.html",
        {
            "order": order
        }
    )

    text_content = (
        f"Hi {order.customer_name},\n\n"
        f"Thank you for shopping with Boww & Meow!\n\n"
        f"Order #{order.id}\n"
        f"Total: ₹{order.total_amount}\n"
        f"Payment: {order.get_payment_method_display()}\n"
        f"Delivery Address: {order.address}\n\n"
        f"Thank you,\n"
        f"Boww & Meow"
    )

    send_brevo_email(
    to_email=order.email,
    to_name=order.customer_name,
    subject=subject,
    html_content=html_content,
)

def send_order_status_email(order):

    if not order.email:
        return

    subject_map = {
        "confirmed":
            f"Order #{order.id} Confirmed 🎉",

        "shipped":
            f"Order #{order.id} Has Been Shipped 📦",

        "delivered":
            f"Order #{order.id} Delivered ✅",

        "cancelled":
            f"Order #{order.id} Cancelled",
    }

    subject = subject_map.get(
        order.status,
        f"Update for Order #{order.id}"
    )

    html_content = render_to_string(
        "store/emails/order_status_update.html",
        {
            "order": order
        }
    )

    text_content = (
        f"Hi {order.customer_name},\n\n"
        f"Your order #{order.id} has been updated.\n\n"
        f"Status: {order.get_status_display()}\n"
        f"Total: ₹{order.total_amount}\n\n"
        f"Thank you,\n"
        f"Boww & Meow"
    )

    send_brevo_email(
        to_email=order.email,
        to_name=order.customer_name,
        subject=subject,
        html_content=html_content,
    )

def checkout(request):
    cart_items, subtotal = _build_cart_items(request)
    pricing = _cart_pricing(request, subtotal)
    total = pricing["total"]
    if not cart_items:
        return redirect("cart")

    checkout_token = request.session.get("checkout_token")
    if not checkout_token:
        checkout_token = str(uuid.uuid4())
        request.session["checkout_token"] = checkout_token

    default_address = None
    addresses = []
    if request.user.is_authenticated:
        default_address = Address.objects.filter(user=request.user, is_default=True).first()
        addresses = Address.objects.filter(user=request.user).order_by("-is_default", "-created_at")

    if request.method == "POST":
        submitted_token = request.POST.get("checkout_token")
        session_token = request.session.get("checkout_token")
        if not submitted_token or submitted_token != session_token:
            return redirect("cart")

        for item in cart_items:
            if Product.objects.filter(id=item["product"].id, is_archived=True).exists():
                return redirect("cart")
            if item["variant"]:
                fresh = ProductVariant.objects.filter(id=item["variant"].id, product=item["product"]).first()
                if not fresh or not fresh.is_available or item["quantity"] > fresh.stock:
                    return render(request, "store/checkout.html", {
                        "cart_items": cart_items, "total": total,
                        "default_address": default_address, "addresses": addresses,
                        "checkout_token": checkout_token,
                        "error": f"The selected size for {item['product'].name} does not have enough stock.",
                    })
            else:
                fresh = Product.objects.get(id=item["product"].id)
                if fresh.is_archived or not fresh.is_available or item["quantity"] > fresh.stock:
                    return render(request, "store/checkout.html", {
                        "cart_items": cart_items, "total": total,
                        "default_address": default_address, "addresses": addresses,
                        "checkout_token": checkout_token,
                        "error": f"Only {fresh.stock} unit(s) of {fresh.name} are available.",
                    })

        selected_address_id = request.POST.get("saved_address")
        selected_address = None
        if request.user.is_authenticated and selected_address_id:
            selected_address = Address.objects.filter(id=selected_address_id, user=request.user).first()

        if selected_address:
            customer_name = selected_address.full_name
            phone = selected_address.phone
            parts = [
                selected_address.address_line1,
                selected_address.address_line2,
                selected_address.city,
                selected_address.state,
            ]
            address = ", ".join(part for part in parts if part)
            address += f" - {selected_address.pincode}"
        else:
            customer_name = request.POST.get("customer_name")
            phone = request.POST.get("phone")
            address = request.POST.get("address")

        email = request.POST.get("email")
        payment_method = request.POST.get("payment_method")

        with transaction.atomic():
            order = Order.objects.create(
                user=request.user if request.user.is_authenticated else None,
                customer_name=customer_name,
                email=email,
                phone=phone,
                address=address,
                payment_method=payment_method,
                payment_status="pending",
                total_amount=total,
                subtotal_amount=subtotal,
                discount_amount=pricing["discount"],
                coupon_code=pricing["coupon"].code if pricing["coupon"] else "",
            )

            order_access_ids = request.session.get("order_access_ids", [])
            order_access_ids = [
                stored_id for stored_id in order_access_ids
                if isinstance(stored_id, int)
            ]
            if order.id not in order_access_ids:
                order_access_ids.append(order.id)
            request.session["order_access_ids"] = order_access_ids[-20:]

            for item in cart_items:
                OrderItem.objects.create(
                    order=order,
                    product=item["product"],
                    variant=item["variant"],
                    variant_size=item["variant"].size if item["variant"] else "",
                    quantity=item["quantity"],
                    price=item["unit_price"],
                )

            _reserve_order_inventory(order)

            if pricing["coupon"]:
                Coupon.objects.filter(pk=pricing["coupon"].pk).update(times_used=F("times_used") + 1)

        request.session.pop("checkout_token", None)
        request.session.pop("coupon_code", None)

        if payment_method == "online":
            client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))
            amount_in_paise = int(total * 100)
            try:
                razorpay_order = client.order.create({
                    "amount": amount_in_paise,
                    "currency": "INR",
                    "receipt": f"bows_meows_{order.id}",
                    "payment_capture": 1,
                })
            except Exception:
                _restore_order_inventory(order)
                order.payment_status = "failed"
                order.save(update_fields=["payment_status"])
                return render(request, "store/payment_failed.html", {
                    "order": order,
                    "error": "We couldn't start the payment. Please try again."
                })

            request.session["current_order_id"] = order.id
            request.session["razorpay_order_id"] = razorpay_order["id"]

            return render(request, "store/payment.html", {
                "order": order,
                "razorpay_order_id": razorpay_order["id"],
                "razorpay_key_id": settings.RAZORPAY_KEY_ID,
                "amount": amount_in_paise,
            })

        if payment_method == "cod":
            send_order_confirmation(order)
            request.session["cart"] = {}
            return redirect("order_success", order_id=order.id)

    return render(request, "store/checkout.html", {
        "cart_items": cart_items,
        "available_coupons": _available_coupons(subtotal),
        **pricing,
        "default_address": default_address,
        "addresses": addresses,
        "checkout_token": checkout_token,
    })

def order_success(request, order_id):
    order = get_object_or_404(Order, id=order_id)
    if not _request_can_access_order(request, order):
        return redirect("home")

    display_subtotal = order.subtotal_amount
    if not display_subtotal:
        display_subtotal = order.total_amount + order.discount_amount

    return render(
        request,
        "store/order_success.html",
        {"order": order, "display_subtotal": display_subtotal}
    )

def register_view(request):

    if request.method == "POST":

        email = request.POST.get("email", "").strip().lower()
        password = request.POST.get("password") or request.POST.get("password1", "")
        password2 = request.POST.get("password2", password)
        full_name = request.POST.get("full_name", "").strip()

        if User.objects.filter(email__iexact=email).exists():
            return render(
                request,
                "store/register.html",
                {"error": "An account with this email already exists."}
                )

        if password != password2:
            return render(request, "store/register.html", {
                "error": "The passwords do not match.", "email_value": email, "full_name_value": full_name,
            })
        try:
            validate_password(password)
        except ValidationError as exc:
            return render(request, "store/register.html", {
                "error": " ".join(exc.messages), "email_value": email, "full_name_value": full_name,
            })

        base_username = re.sub(r"[^a-zA-Z0-9._-]", "", email.split("@")[0]) or "petparent"
        username = base_username[:140]
        suffix = 1
        while User.objects.filter(username=username).exists():
            suffix += 1
            username = f"{base_username[:130]}-{suffix}"

        user = User.objects.create_user(
                        username=username,
                        email=email,
                        password=password
                    )
        if full_name:
            names = full_name.split(None, 1)
            user.first_name = names[0]
            user.last_name = names[1] if len(names) > 1 else ""
            user.save(update_fields=["first_name", "last_name"])

        login(request, user, backend="django.contrib.auth.backends.ModelBackend")

        return redirect("home")

    return render(
        request,
        "store/register.html"
    )

def login_view(request):
    if request.method == "POST":
        identifier = (request.POST.get("identifier") or request.POST.get("username") or "").strip()
        password = request.POST.get("password")

        matched_user = User.objects.filter(email__iexact=identifier).first()
        username = matched_user.username if matched_user else identifier

        user = authenticate(
            request,
            username=username,
            password=password
        )

        if user is not None:
            login(request, user)
            if request.POST.get("remember_me"):
                request.session.set_expiry(60 * 60 * 24 * 30)
            else:
                request.session.set_expiry(0)

            next_url = request.POST.get("next") or request.GET.get("next")

            if next_url and url_has_allowed_host_and_scheme(
                next_url,
                allowed_hosts={request.get_host()},
                require_https=request.is_secure(),
            ):
                return redirect(next_url)

            return redirect("home")

        return render(
            request,
            "store/login.html",
            {"error": "We couldn't match that email and password.", "identifier_value": identifier}
        )

    return render(request, "store/login.html")


@require_POST
def logout_view(request):
    logout(request)
    return redirect("home")


@login_required
def account(request):
    return render(request, "store/account.html")

@login_required
def my_pets(request):
    pets = Pet.objects.filter(owner=request.user)

    return render(
        request,
        "store/my_pets.html",
        {"pets": pets}
    )


@login_required
def add_pet(request):
    if request.method == "POST":
        pet_image = request.FILES.get("image")
        if pet_image:
            try:
                _validate_uploaded_product_image(pet_image)
            except ValueError as exc:
                return render(request, "store/add_pet.html", {"error": str(exc)})
        Pet.objects.create(
            owner=request.user,
            name=request.POST.get("name"),
            pet_type=request.POST.get("pet_type"),
            breed=request.POST.get("breed"),
            age=request.POST.get("age") or None,
            weight=request.POST.get("weight") or None,
            notes=request.POST.get("notes"),
            image=pet_image,
        )

        return redirect("my_pets")

    return render(request, "store/add_pet.html")


@login_required
def edit_pet(request, pet_id):
    pet = get_object_or_404(Pet, id=pet_id, owner=request.user)

    if request.method == "POST":
        pet_image = request.FILES.get("image")
        if pet_image:
            try:
                _validate_uploaded_product_image(pet_image)
            except ValueError as exc:
                return render(request, "store/edit_pet.html", {"pet": pet, "error": str(exc)})

        pet.name = request.POST.get("name", "").strip()
        pet.pet_type = request.POST.get("pet_type")
        pet.breed = request.POST.get("breed", "").strip()
        pet.age = request.POST.get("age") or None
        pet.weight = request.POST.get("weight") or None
        pet.notes = request.POST.get("notes", "").strip()
        if request.POST.get("remove_image") == "on":
            pet.image = None
        elif pet_image:
            pet.image = pet_image
        pet.save()
        messages.success(request, f"{pet.name}'s profile was updated.")
        return redirect("my_pets")

    return render(request, "store/edit_pet.html", {"pet": pet})

@login_required
def my_orders(request):
    orders = Order.objects.filter(
        user=request.user
    ).order_by("-created_at")

    return render(
        request,
        "store/my_orders.html",
        {"orders": orders}
    )


@login_required
@require_POST
def reorder(request, order_id):
    order = get_object_or_404(
        Order.objects.prefetch_related("items__product", "items__variant"),
        id=order_id,
        user=request.user,
    )
    new_cart = {}
    skipped = []
    adjusted = []

    for item in order.items.all():
        product = item.product
        if product.is_archived or not product.is_available or product.requires_prescription:
            skipped.append(product.name)
            continue

        variant = item.variant
        if item.variant_size:
            if not variant or variant.product_id != product.id:
                variant = product.variants.filter(size__iexact=item.variant_size).first()
            if not variant or not variant.is_available or variant.stock <= 0:
                skipped.append(f"{product.name} ({item.variant_size})")
                continue
            stock = variant.stock
        else:
            # Products that now require a package choice cannot be safely
            # substituted for an old non-variant order line.
            if product.variants.exists():
                skipped.append(product.name)
                continue
            variant = None
            stock = product.stock

        if stock <= 0:
            skipped.append(product.name)
            continue
        quantity = min(item.quantity, stock)
        if quantity < item.quantity:
            adjusted.append(f"{product.name} (quantity changed to {quantity})")
        line_key = _cart_line_key(product.id, variant.id if variant else None)
        new_cart[line_key] = {
            "product_id": product.id,
            "variant_id": variant.id if variant else None,
            "quantity": quantity,
        }

    if not new_cart:
        messages.error(request, "None of the products in this order are currently available to reorder.")
        return redirect("order_detail", order_id=order.id)

    request.session["cart"] = new_cart
    request.session.pop("coupon_code", None)
    request.session.pop("checkout_token", None)
    request.session.modified = True
    if skipped:
        messages.warning(request, "Unavailable items were left out: " + ", ".join(skipped) + ".")
    if adjusted:
        messages.warning(request, "Stock changed for: " + ", ".join(adjusted) + ".")
    messages.success(request, f"Order BM-{order.id:04d} was added to your cart. Please confirm current prices before paying.")
    return redirect("checkout")
@login_required
def order_detail(request, order_id):
    order = get_object_or_404(
        Order,
        id=order_id,
        user=request.user
    )

    return render(
        request,
        "store/order_detail.html",
        {"order": order}
    )

@login_required
def crm_dashboard(request):

    if not request.user.is_staff:
        return redirect("home")

    total_customers = User.objects.filter(is_staff=False).count()
    total_orders = Order.objects.count()

    total_revenue = Order.objects.filter(
        status__in=["confirmed", "shipped", "delivered"]
    ).aggregate(
        total=Sum("total_amount")
    )["total"] or 0

    low_stock_products = Product.objects.filter(
        stock__lte=5
    ).order_by("stock")

    recent_orders = Order.objects.order_by(
        "-created_at"
    )[:8]

    context = {
        "total_customers": total_customers,
        "total_orders": total_orders,
        "total_revenue": total_revenue,
        "low_stock_products": low_stock_products,
        "recent_orders": recent_orders,
    }

    return render(
        request,
        "store/crm_dashboard.html",
        context
    )


@login_required
def crm_coupons(request):
    if not request.user.is_staff:
        return redirect("home")
    if request.method == "POST":
        action = request.POST.get("action", "create")
        if action == "toggle":
            coupon = get_object_or_404(Coupon, pk=request.POST.get("coupon_id"))
            coupon.is_active = not coupon.is_active
            coupon.save(update_fields=["is_active"])
            messages.success(request, f"{coupon.code} {'activated' if coupon.is_active else 'paused'}.")
        else:
            try:
                percent = int(request.POST.get("discount_percent", 0))
                if not 1 <= percent <= 100:
                    raise ValueError
                Coupon.objects.create(
                    code=request.POST.get("code", "").strip().upper(),
                    discount_percent=percent,
                    minimum_order=Decimal(request.POST.get("minimum_order") or "0"),
                    maximum_discount=(
                        Decimal(request.POST["maximum_discount"])
                        if request.POST.get("maximum_discount")
                        and Decimal(request.POST["maximum_discount"]) > 0
                        else None
                    ),
                    usage_limit=int(request.POST["usage_limit"]) if request.POST.get("usage_limit") else None,
                )
                messages.success(request, "Coupon created and ready to use.")
            except (ValueError, InvalidOperation):
                messages.error(request, "Enter valid coupon values. Discount must be between 1% and 100%.")
            except Exception:
                messages.error(request, "That coupon code already exists or could not be saved.")
        return redirect("crm_coupons")
    return render(request, "store/crm_coupons.html", {"coupons": Coupon.objects.all()})

@login_required
def crm_customers(request):

    if not request.user.is_staff:
        return redirect("home")

    customers = User.objects.filter(
        is_staff=False
    ).order_by("-date_joined")

    return render(
        request,
        "store/crm_customers.html",
        {"customers": customers}
    )
@login_required
def crm_customer_detail(request, user_id):

    if not request.user.is_staff:
        return redirect("home")

    customer = get_object_or_404(
        User,
        id=user_id,
        is_staff=False
    )

    orders = Order.objects.filter(
        user=customer
    ).order_by("-created_at")

    pets = Pet.objects.filter(
        owner=customer
    )

    total_spent = orders.aggregate(
        total=Sum("total_amount")
    )["total"] or 0

    context = {
        "customer": customer,
        "orders": orders,
        "pets": pets,
        "total_spent": total_spent,
    }

    return render(
        request,
        "store/crm_customer_detail.html",
        context
    )
@login_required
def crm_inventory(request):
    if not request.user.is_staff:
        return redirect("home")

    products = Product.objects.all().order_by("name")

    search_query = request.GET.get("q")
    category_filter = request.GET.get("category")
    low_stock = request.GET.get("low_stock")
    archive_filter = request.GET.get("archive", "active")

    if archive_filter == "archived":
        products = products.filter(is_archived=True)
    elif archive_filter == "all":
        pass
    else:
        products = products.filter(is_archived=False)

    if search_query:
        products = products.filter(
            name__icontains=search_query
        )

    if category_filter:
        products = products.filter(
            category=category_filter
        )

    if low_stock == "yes":
        products = products.filter(
            stock__lte=5
        )

    context = {
        "products": products,
        "search_query": search_query or "",
        "category_filter": category_filter or "",
        "low_stock": low_stock or "",
        "archive_filter": archive_filter,
    }

    return render(
        request,
        "store/crm_inventory.html",
        context
    )



@login_required
def crm_inventory_edit(request, product_id):
    if not request.user.is_staff:
        return redirect("home")

    product = get_object_or_404(Product, id=product_id)

    if request.method == "POST":
        product.name = request.POST.get("name")
        product.brand = request.POST.get("brand", "").strip()
        product.pet_type = request.POST.get("pet_type", "")
        product.product_type = request.POST.get("product_type", "")
        product.care_area = request.POST.get("care_area", "")
        product.category = request.POST.get("category")
        product.life_stage = request.POST.get("life_stage", "")
        product.flavour = request.POST.get("flavour", "").strip()
        product.key_benefits = request.POST.get("key_benefits", "").strip()
        product.target_species = request.POST.get("target_species", "").strip()
        product.active_ingredients = request.POST.get("active_ingredients", "").strip()
        product.usage_warning = request.POST.get("usage_warning", "").strip()
        product.requires_prescription = request.POST.get("requires_prescription") == "on"
        product.price = request.POST.get("price")
        product.original_price = request.POST.get("original_price") or None
        product.stock = request.POST.get("stock") or 0
        product.description = request.POST.get("description", "").strip()
        for field in ("manufacturer_name", "manufacturer_address", "country_of_origin", "marketed_by", "ingredients", "directions", "specifications"):
            setattr(product, field, request.POST.get(field, "").strip())
        product.is_available = request.POST.get("is_available") == "on"
        product.is_featured = request.POST.get("is_featured") == "on"
        new_image = request.FILES.get("image")
        if new_image:
            product.image = new_image
        product.save()

        ids = request.POST.getlist("existing_variant_id")
        sizes = request.POST.getlist("existing_variant_size")
        prices = request.POST.getlist("existing_variant_price")
        mrps = request.POST.getlist("existing_variant_original_price")
        stocks = request.POST.getlist("existing_variant_stock")
        skus = request.POST.getlist("existing_variant_sku")

        for i, variant_id in enumerate(ids):
            variant = ProductVariant.objects.filter(id=variant_id, product=product).first()
            if not variant:
                continue
            variant.size = sizes[i].strip()
            variant.price = prices[i] or 0
            variant.original_price = mrps[i] or None
            variant.stock = stocks[i] or 0
            variant.sku = skus[i].strip() or None
            variant.is_available = int(variant.stock) > 0
            new_variant_image = request.FILES.get(
                f"existing_variant_image_{variant.id}"
            )
            if new_variant_image:
                variant.image = new_variant_image
            variant.save()

        delete_ids = request.POST.getlist("delete_variant")
        if delete_ids:
            ProductVariant.objects.filter(id__in=delete_ids, product=product).delete()

        new_sizes = request.POST.getlist("variant_size")
        new_prices = request.POST.getlist("variant_price")
        new_mrps = request.POST.getlist("variant_original_price")
        new_stocks = request.POST.getlist("variant_stock")
        new_skus = request.POST.getlist("variant_sku")

        for i, size in enumerate(new_sizes):
            size = size.strip()
            if not size or i >= len(new_prices) or not new_prices[i]:
                continue
            variant_stock = new_stocks[i] if i < len(new_stocks) and new_stocks[i] else 0
            ProductVariant.objects.create(
                product=product,
                size=size,
                price=new_prices[i],
                original_price=new_mrps[i] if i < len(new_mrps) and new_mrps[i] else None,
                stock=variant_stock,
                sku=new_skus[i].strip() if i < len(new_skus) and new_skus[i].strip() else None,
                is_available=int(variant_stock) > 0,
            )

        if product.variants.exists():
            _sync_product_stock(product)
        # ==========================================
# UPDATE EXISTING FEEDING GUIDE ROWS
# ==========================================

        feeding_ids = request.POST.getlist(
            "existing_feeding_id"
        )

        feeding_min_weights = request.POST.getlist(
            "existing_feeding_min_weight"
        )

        feeding_max_weights = request.POST.getlist(
            "existing_feeding_max_weight"
        )

        feeding_daily_grams = request.POST.getlist(
            "existing_feeding_daily_grams"
        )


        for i, guide_id in enumerate(feeding_ids):

            guide = FeedingGuide.objects.filter(
                id=guide_id,
                product=product
            ).first()

            if not guide:
                continue

            guide.min_weight = feeding_min_weights[i]
            guide.max_weight = feeding_max_weights[i]
            guide.daily_grams = feeding_daily_grams[i]

            guide.save()


        # ==========================================
        # DELETE FEEDING GUIDE ROWS
        # ==========================================

        delete_guide_ids = request.POST.getlist(
            "delete_feeding_guide"
        )

        if delete_guide_ids:

            FeedingGuide.objects.filter(
                id__in=delete_guide_ids,
                product=product
            ).delete()


        # ==========================================
        # ADD NEW FEEDING GUIDE ROWS
        # ==========================================

        min_weights = request.POST.getlist(
            "feeding_min_weight"
        )

        max_weights = request.POST.getlist(
            "feeding_max_weight"
        )

        daily_grams = request.POST.getlist(
            "feeding_daily_grams"
        )


        for i, min_weight in enumerate(min_weights):

            if not min_weight:
                continue

            if (
                i >= len(max_weights)
                or not max_weights[i]
                or i >= len(daily_grams)
                or not daily_grams[i]
            ):
                continue

            FeedingGuide.objects.create(
                product=product,
                min_weight=min_weight,
                max_weight=max_weights[i],
                daily_grams=daily_grams[i],
            )
        return redirect("crm_inventory")

    return render(
        request,
        "store/crm_inventory_edit.html",
        {
            "product": product,
            "variants": product.variants.all(),
            "feeding_guides": (
                product.feeding_guides
                .all()
                .order_by("min_weight")
            ),
        }
    )

@login_required
def crm_orders(request):
    if not request.user.is_staff:
        return redirect("home")

    orders = Order.objects.all().order_by("-created_at")

    search_query = request.GET.get("q")
    status_filter = request.GET.get("status")

    if search_query:
        orders = orders.filter(
            customer_name__icontains=search_query
        )

    if status_filter:
        orders = orders.filter(
            status=status_filter
        )

    context = {
        "orders": orders,
        "search_query": search_query or "",
        "status_filter": status_filter or "",
    }

    return render(
        request,
        "store/crm_orders.html",
        context
    )



@login_required
def crm_order_status(request, order_id):
    if not request.user.is_staff:
        return redirect("home")

    order = get_object_or_404(Order, id=order_id)
    if request.method != "POST":
        return redirect("crm_orders")

    new_status = request.POST.get("status")
    valid_statuses = ["pending", "confirmed", "shipped", "delivered", "cancelled"]
    if new_status not in valid_statuses:
        return redirect("crm_orders")

    old_status = order.status

    if new_status == "cancelled" and old_status != "cancelled":
        _restore_order_inventory(order)

    elif old_status == "cancelled" and new_status != "cancelled":
        try:
            _reserve_order_inventory(order)
        except ValueError:
            return redirect("crm_orders")

    order.status = new_status
    if order.payment_method == "cod":
        if new_status == "delivered":
            order.payment_status = "paid"
        elif new_status == "cancelled" and order.payment_status != "paid":
            order.payment_status = "pending"
    order.save()

    if old_status != new_status:
        send_order_status_email(order)

    return redirect("crm_orders")

@login_required
def crm_reports(request):
    if not request.user.is_staff:
        return redirect("home")

    period = request.GET.get("period", "30")

    now = timezone.now()

    if period == "7":
        start_date = now - timedelta(days=7)

    elif period == "30":
        start_date = now - timedelta(days=30)

    elif period == "year":
        start_date = now.replace(
            month=1,
            day=1,
            hour=0,
            minute=0,
            second=0,
            microsecond=0
        )

    else:
        start_date = None

    orders_queryset = Order.objects.filter(
        status__in=["confirmed", "shipped", "delivered"]
    )

    if start_date:
        orders_queryset = orders_queryset.filter(
            created_at__gte=start_date
        )
    total_revenue = orders_queryset.aggregate(
        total=Sum("total_amount")
    )["total"] or 0
    daily_sales = (
        orders_queryset
        .annotate(
            day=TruncDate("created_at")
        )
        .values("day")
        .annotate(
            revenue=Sum("total_amount"),
            orders=Count("id")
        )
        .order_by("day")
    )
    total_revenue = Order.objects.filter(
        status__in=["confirmed", "shipped", "delivered"]
    ).aggregate(
        total=Sum("total_amount")
    )["total"] or 0

    total_orders = orders_queryset.count()

    delivered_orders = Order.objects.filter(
        status="delivered"
    ).count()

    cancelled_orders = Order.objects.filter(
        status="cancelled"
    ).count()

    top_products = (
        OrderItem.objects
        .filter(
            order__status__in=["confirmed", "shipped", "delivered"]
        )
        .values("product__name")
        .annotate(
            quantity_sold=Sum("quantity"),
            revenue=Sum(
                ExpressionWrapper(
                    F("price") * F("quantity"),
                    output_field=DecimalField(
                        max_digits=12,
                        decimal_places=2
                    )
                )
            )
        )
        .order_by("-quantity_sold")[:5]
    )
    daily_sales = (
        Order.objects
        .filter(
            status__in=["confirmed", "shipped", "delivered"]
        )
        .annotate(
            day=TruncDate("created_at")
        )
        .values("day")
        .annotate(
            revenue=Sum("total_amount"),
            orders=Count("id")
        )
        .order_by("day")
    )
    top_customers = (
        Order.objects
        .filter(
            user__isnull=False,
            status__in=["confirmed", "shipped", "delivered"]
        )
        .values("user__username")
        .annotate(
            total_spent=Sum("total_amount"),
            order_count=Count("id")
        )
        .order_by("-total_spent")[:5]
    )

    context = {
        "total_revenue": total_revenue,
        "total_orders": total_orders,
        "delivered_orders": delivered_orders,
        "cancelled_orders": cancelled_orders,
        "top_products": top_products,
        "top_customers": top_customers,
        "daily_sales": daily_sales,
        "period": period,
    }

    return render(
        request,
        "store/crm_reports.html",
        context
    )

@login_required
def crm_inventory_add(request):

    if not request.user.is_staff:
        return redirect("home")

    if request.method == "POST":

        # ==========================================
        # CREATE MAIN PRODUCT
        # ==========================================

        product = Product.objects.create(

            name=request.POST.get("name"),

            brand=request.POST.get(
                "brand",
                ""
            ).strip(),

            pet_type=request.POST.get(
                "pet_type",
                ""
            ),

            product_type=request.POST.get("product_type", ""),
            care_area=request.POST.get("care_area", ""),

            category=request.POST.get(
                "category"
            ),

            life_stage=request.POST.get(
                "life_stage",
                ""
            ),

            flavour=request.POST.get(
                "flavour",
                ""
            ).strip(),

            key_benefits=request.POST.get(
                "key_benefits",
                ""
            ).strip(),

            target_species=request.POST.get(
                "target_species",
                ""
            ).strip(),

            active_ingredients=request.POST.get(
                "active_ingredients",
                ""
            ).strip(),

            usage_warning=request.POST.get(
                "usage_warning",
                ""
            ).strip(),

            requires_prescription=(
                request.POST.get("requires_prescription") == "on"
            ),

            price=request.POST.get(
                "price"
            ),

            original_price=(
                request.POST.get(
                    "original_price"
                )
                or None
            ),

            stock=(
                request.POST.get(
                    "stock"
                )
                or 0
            ),

            description=request.POST.get(
                "description",
                ""
            ).strip(),
            manufacturer_name=request.POST.get("manufacturer_name", "").strip(),
            manufacturer_address=request.POST.get("manufacturer_address", "").strip(),
            country_of_origin=request.POST.get("country_of_origin", "").strip(),
            marketed_by=request.POST.get("marketed_by", "").strip(),
            ingredients=request.POST.get("ingredients", "").strip(),
            directions=request.POST.get("directions", "").strip(),
            specifications=request.POST.get("specifications", "").strip(),

            image=request.FILES.get(
                "image"
            ),

            is_available=(
                request.POST.get(
                    "is_available"
                )
                == "on"
            ),

            is_featured=(
                request.POST.get(
                    "is_featured"
                )
                == "on"
            ),
        )


        # ==========================================
        # GET VARIANT FORM DATA
        # ==========================================

        sizes = request.POST.getlist(
            "variant_size"
        )

        prices = request.POST.getlist(
            "variant_price"
        )

        mrps = request.POST.getlist(
            "variant_original_price"
        )

        stocks = request.POST.getlist(
            "variant_stock"
        )

        skus = request.POST.getlist(
            "variant_sku"
        )

        variant_images = request.FILES.getlist(
            "variant_image"
        )


        # ==========================================
        # CREATE VARIANTS
        # ==========================================

        for i, size in enumerate(sizes):

            size = size.strip()

            if not size:
                continue

            if (
                i >= len(prices)
                or not prices[i]
            ):
                continue


            variant_stock = (
                stocks[i]
                if (
                    i < len(stocks)
                    and stocks[i]
                )
                else 0
            )


            variant_image = request.FILES.get(f"variant_image_{i}")
            variant_price = prices[i]
            variant_mrp = (
                mrps[i]
                if i < len(mrps) and mrps[i]
                else None
            )
            sku = (
                skus[i].strip()
                if i < len(skus) and skus[i].strip()
                else None
            )

            ProductVariant.objects.create(
                product=product,
                size=size,
                image=variant_image,
                price=variant_price,
                original_price=variant_mrp,
                stock=variant_stock,
                sku=sku,
                is_available=int(variant_stock) > 0,
            )

        # ==========================================
        # FEEDING GUIDE
        # ==========================================

        min_weights = request.POST.getlist(
            "feeding_min_weight"
        )

        max_weights = request.POST.getlist(
            "feeding_max_weight"
        )

        daily_grams = request.POST.getlist(
            "feeding_daily_grams"
        )


        for i, min_weight in enumerate(
            min_weights
        ):

            if not min_weight:
                continue

            if (
                i >= len(max_weights)
                or not max_weights[i]
                or i >= len(daily_grams)
                or not daily_grams[i]
            ):
                continue

            FeedingGuide.objects.create(

                product=product,

                min_weight=min_weight,

                max_weight=max_weights[i],

                daily_grams=daily_grams[i],
            )


        # ==========================================
        # SYNC MAIN PRODUCT STOCK
        # ==========================================

        if product.variants.exists():

            product.stock = sum(
                variant.stock
                for variant
                in product.variants.all()
            )

            product.is_available = (
                product.stock > 0
            )

            product.save(
                update_fields=[
                    "stock",
                    "is_available",
                ]
            )


        messages.success(
            request,
            f"Product #{product.id} created. Its bulk main-image filename is {product.id}-main.jpg.",
        )
        return redirect("crm_inventory_edit", product_id=product.id)


    return render(
        request,
        "store/crm_inventory_add.html"
    )
def download_product_image(
    image_url,
    prefix="product"
):

    if not image_url:
        return None

    image_url = image_url.strip()

    parsed = urlparse(
        image_url
    )

    if parsed.scheme not in [
        "http",
        "https"
    ]:
        raise ValueError(
            "Image URL must use http or https."
        )

    response = requests.get(
        image_url,
        timeout=15
    )

    response.raise_for_status()

    content_type = (
        response.headers
        .get(
            "Content-Type",
            ""
        )
        .split(";")[0]
        .lower()
    )

    if not content_type.startswith(
        "image/"
    ):
        raise ValueError(
            f"URL is not an image: {image_url}"
        )


    # Maximum 5 MB
    if len(response.content) > (
        5 * 1024 * 1024
    ):
        raise ValueError(
            "Image is larger than 5 MB."
        )


    extension = (
        mimetypes.guess_extension(
            content_type
        )
    )

    if not extension:

        extension = (
            urlparse(image_url)
            .path
            .split(".")[-1]
        )

        if extension:
            extension = (
                "." + extension
            )
        else:
            extension = ".jpg"


    # ImageField names include their upload directory and are limited to
    # 100 characters by default. Supplier SKUs/product codes can be much
    # longer, so keep a compact, filesystem-safe prefix before adding the
    # random suffix and extension.
    safe_prefix = re.sub(
        r"[^A-Za-z0-9_-]+",
        "-",
        str(prefix),
    ).strip("-_")[:48] or "product"

    filename = (
        f"{safe_prefix}-"
        f"{uuid.uuid4().hex[:12]}"
        f"{extension}"
    )


    return ContentFile(
        response.content,
        name=filename
    )


@login_required
@require_POST
def crm_inventory_archive(request, product_id):
    if not request.user.is_staff:
        return redirect("home")
    product = get_object_or_404(Product, id=product_id)
    product.is_archived = True
    product.save(update_fields=["is_archived"])
    messages.success(request, f"Product #{product.id} archived. Its history and images were preserved.")
    return redirect("crm_inventory")


@login_required
@require_POST
def crm_inventory_restore(request, product_id):
    if not request.user.is_staff:
        return redirect("home")
    product = get_object_or_404(Product, id=product_id)
    product.is_archived = False
    product.save(update_fields=["is_archived"])
    messages.success(request, f"Product #{product.id} restored to inventory.")
    return redirect("crm_inventory")


def _validate_uploaded_product_image(upload):
    if upload.size > 5 * 1024 * 1024:
        raise ValueError("Image is larger than 5 MB.")
    try:
        PillowImage.open(upload).verify()
    except (UnidentifiedImageError, OSError) as exc:
        raise ValueError("File is not a valid image.") from exc
    finally:
        upload.seek(0)
@login_required
def crm_inventory_bulk_import(request):

    if not request.user.is_staff:
        return redirect("home")


    errors = []
    preview = None
    result = None

    action = request.POST.get(
        "action"
    )


    # ==========================================
    # CANCEL PREVIEW
    # ==========================================

    if action == "cancel":

        request.session.pop(
            "bulk_import_rows",
            None
        )

        return redirect(
            "crm_inventory_bulk_import"
        )


    # ==========================================
    # STEP 1 — PREVIEW CSV
    # ==========================================

    if (
        request.method == "POST"
        and action == "preview"
    ):

        uploaded_file = request.FILES.get(
            "csv_file"
        )

        if not uploaded_file:

            errors.append(
                "Please choose a CSV file."
            )

        else:

            try:

                decoded_file = (
                    uploaded_file
                    .read()
                    .decode("utf-8-sig")
                )

                reader = csv.DictReader(
                    io.StringIO(
                        decoded_file
                    )
                )

                rows = list(reader)


                # Save CSV data temporarily
                # so Confirm doesn't need another upload.

                request.session[
                    "bulk_import_rows"
                ] = rows

                request.session.modified = True


                new_product_codes = set()
                existing_product_codes = set()

                new_variants = 0
                existing_variants = 0

                invalid_count = 0

                seen_skus = set()

                product_preview = {}


                for row_number, row in enumerate(
                    rows,
                    start=2
                ):

                    name = (
                        row.get(
                            "name",
                            ""
                        ).strip()
                    )

                    product_code = (
                        row.get(
                            "product_code",
                            ""
                        ).strip()
                    )

                    brand = (
                        row.get(
                            "brand",
                            ""
                        ).strip()
                    )

                    size = (
                        row.get(
                            "size",
                            ""
                        ).strip()
                    )

                    sku = (
                        row.get(
                            "sku",
                            ""
                        ).strip()
                    )

                    variant_price = (
                        row.get(
                            "variant_price",
                            ""
                        ).strip()
                    )


                    row_valid = True


                    if not name:

                        errors.append(
                            f"Row {row_number}: "
                            "Product name is missing."
                        )

                        row_valid = False


                    if not product_code:

                        errors.append(
                            f"Row {row_number}: "
                            "Product code is missing."
                        )

                        row_valid = False


                    if not size:

                        errors.append(
                            f"Row {row_number}: "
                            "Variant size is missing."
                        )

                        row_valid = False


                    if not sku:

                        errors.append(
                            f"Row {row_number}: "
                            "SKU is missing."
                        )

                        row_valid = False


                    if not variant_price:

                        errors.append(
                            f"Row {row_number}: "
                            "Variant price is missing."
                        )

                        row_valid = False


                    # Duplicate SKU inside same CSV

                    if sku:

                        if sku in seen_skus:

                            errors.append(
                                f"Row {row_number}: "
                                f"Duplicate SKU in CSV: "
                                f"{sku}"
                            )

                            row_valid = False

                        else:

                            seen_skus.add(
                                sku
                            )


                    if not row_valid:

                        invalid_count += 1
                        continue


                    # =================================
                    # PRODUCT PREVIEW
                    # =================================

                    if product_code not in product_preview:

                        existing_product = (
                            Product.objects
                            .filter(
                                name=name,
                                brand=brand
                            )
                            .exists()
                        )

                        if existing_product:

                            existing_product_codes.add(
                                product_code
                            )

                        else:

                            new_product_codes.add(
                                product_code
                            )


                        product_preview[
                            product_code
                        ] = {
                            "code":
                                product_code,

                            "name":
                                name,

                            "brand":
                                brand,

                            "variant_count":
                                0,
                        }


                    product_preview[
                        product_code
                    ][
                        "variant_count"
                    ] += 1


                    # =================================
                    # VARIANT PREVIEW
                    # =================================

                    if (
                        ProductVariant.objects
                        .filter(
                            sku=sku
                        )
                        .exists()
                    ):

                        existing_variants += 1

                    else:

                        new_variants += 1


                preview = {

                    "new_products":
                        len(
                            new_product_codes
                        ),

                    "existing_products":
                        len(
                            existing_product_codes
                        ),

                    "new_variants":
                        new_variants,

                    "existing_variants":
                        existing_variants,

                    "invalid_count":
                        invalid_count,

                    "products":
                        list(
                            product_preview.values()
                        ),
                }


            except Exception as e:

                errors.append(
                    f"Could not read CSV: {e}"
                )


    # ==========================================
    # STEP 2 — CONFIRM IMPORT
    # ==========================================

    elif (
        request.method == "POST"
        and action == "confirm"
    ):

        rows = request.session.get(
            "bulk_import_rows"
        )


        if not rows:

            errors.append(
                "Import preview expired. "
                "Please upload the CSV again."
            )

        else:

            created_products = 0
            created_variants = 0
            updated_variants = 0

            product_cache = {}


            try:

                with transaction.atomic():

                    for row_number, row in enumerate(
                        rows,
                        start=2
                    ):

                        name = (
                            row.get(
                                "name",
                                ""
                            ).strip()
                        )

                        product_code = (
                            row.get(
                                "product_code",
                                ""
                            ).strip()
                        )

                        brand = (
                            row.get(
                                "brand",
                                ""
                            ).strip()
                        )

                        size = (
                            row.get(
                                "size",
                                ""
                            ).strip()
                        )

                        sku = (
                            row.get(
                                "sku",
                                ""
                            ).strip()
                        )


                        if (
                            not name
                            or not product_code
                            or not size
                            or not sku
                        ):
                            continue


                        feeding_guide_raw = (
                            row.get(
                                "feeding_guide",
                                ""
                            ).strip()
                        )


                        product_image_url = (
                            row.get(
                                "product_image_url",
                                ""
                            ).strip()
                        )


                        variant_image_url = (
                            row.get(
                                "variant_image_url",
                                ""
                            ).strip()
                        )


                        # =================================
                        # PRODUCT
                        # =================================

                        if product_code in product_cache:

                            product = (
                                product_cache[
                                    product_code
                                ]
                            )

                        else:

                            product = (
                                Product.objects
                                .filter(
                                    name=name,
                                    brand=brand
                                )
                                .first()
                            )


                            if not product:

                                product = (
                                    Product.objects.create(

                                        name=name,

                                        brand=brand,

                                        pet_type=row.get(
                                            "pet_type",
                                            ""
                                        ).strip(),

                                        category=row.get(
                                            "category",
                                            ""
                                        ).strip(),

                                        life_stage=row.get(
                                            "life_stage",
                                            ""
                                        ).strip(),

                                        flavour=row.get(
                                            "flavour",
                                            ""
                                        ).strip(),

                                        description=row.get(
                                            "description",
                                            ""
                                        ).strip(),

                                        manufacturer_name=row.get("manufacturer_name", "").strip(),
                                        manufacturer_address=row.get("manufacturer_address", "").replace(" | ", "\n").strip(),
                                        country_of_origin=row.get("country_of_origin", "").strip(),
                                        marketed_by=row.get("marketed_by", "").strip(),
                                        ingredients=row.get("ingredients", "").replace(" | ", "\n").strip(),
                                        directions=row.get("directions", "").replace(" | ", "\n").strip(),
                                        specifications=row.get("specifications", "").replace(" | ", "\n").strip(),

                                        key_benefits=row.get(
                                            "key_benefits",
                                            ""
                                        ).replace(
                                            " | ",
                                            "\n"
                                        ),

                                        price=(
                                            row.get(
                                                "base_price"
                                            )
                                            or 0
                                        ),

                                        original_price=(
                                            row.get(
                                                "base_mrp"
                                            )
                                            or None
                                        ),

                                        stock=0,

                                        is_featured=(
                                            row.get(
                                                "featured",
                                                ""
                                            ).lower()
                                            in [
                                                "yes",
                                                "true",
                                                "1",
                                            ]
                                        ),

                                        is_available=True,
                                    )
                                )

                                created_products += 1


                            # MAIN PRODUCT IMAGE

                            if (
                                product_image_url
                                and not product.image
                            ):

                                try:

                                    image_file = (
                                        download_product_image(
                                            product_image_url,
                                            prefix=
                                                product_code
                                        )
                                    )

                                    if image_file:

                                        product.image.save(
                                            image_file.name,
                                            image_file,
                                            save=True
                                        )

                                except Exception as image_error:

                                    errors.append(
                                        f"Row {row_number}: "
                                        f"Product image failed - "
                                        f"{image_error}"
                                    )


                            product_cache[
                                product_code
                            ] = product


                        # =================================
                        # FEEDING GUIDE
                        # =================================

                        if feeding_guide_raw:

                            try:

                                guide_parts = (
                                    feeding_guide_raw
                                    .split("|")
                                )

                                for guide_part in guide_parts:

                                    guide_part = (
                                        guide_part.strip()
                                    )

                                    if not guide_part:
                                        continue


                                    weight_range, grams = (
                                        guide_part.split(
                                            ":",
                                            1
                                        )
                                    )


                                    min_weight, max_weight = (
                                        weight_range.split(
                                            "-",
                                            1
                                        )
                                    )


                                    FeedingGuide.objects.update_or_create(

                                        product=product,

                                        min_weight=
                                            min_weight.strip(),

                                        max_weight=
                                            max_weight.strip(),

                                        defaults={
                                            "daily_grams":
                                                grams.strip()
                                        }
                                    )


                            except Exception as feeding_error:

                                errors.append(
                                    f"Row {row_number}: "
                                    f"Feeding guide failed - "
                                    f"{feeding_error}"
                                )


                        # =================================
                        # VARIANT
                        # =================================

                        variant = (
                            ProductVariant.objects
                            .filter(
                                sku=sku
                            )
                            .first()
                        )


                        variant_stock = int(
                            row.get(
                                "variant_stock"
                            )
                            or 0
                        )


                        if variant:

                            variant.size = size

                            variant.price = (
                                row.get(
                                    "variant_price"
                                )
                                or 0
                            )

                            variant.original_price = (
                                row.get(
                                    "variant_mrp"
                                )
                                or None
                            )

                            variant.stock = (
                                variant_stock
                            )

                            variant.is_available = (
                                variant_stock > 0
                            )


                            if variant_image_url:

                                try:

                                    image_file = (
                                        download_product_image(
                                            variant_image_url,
                                            prefix=sku
                                        )
                                    )

                                    if image_file:

                                        variant.image.save(
                                            image_file.name,
                                            image_file,
                                            save=False
                                        )

                                except Exception as image_error:

                                    errors.append(
                                        f"Row {row_number}: "
                                        f"Variant image failed - "
                                        f"{image_error}"
                                    )


                            variant.save()

                            updated_variants += 1


                        else:

                            variant = (
                                ProductVariant.objects.create(

                                    product=product,

                                    size=size,

                                    price=(
                                        row.get(
                                            "variant_price"
                                        )
                                        or 0
                                    ),

                                    original_price=(
                                        row.get(
                                            "variant_mrp"
                                        )
                                        or None
                                    ),

                                    stock=
                                        variant_stock,

                                    sku=sku,

                                    is_available=(
                                        variant_stock > 0
                                    ),
                                )
                            )


                            if variant_image_url:

                                try:

                                    image_file = (
                                        download_product_image(
                                            variant_image_url,
                                            prefix=sku
                                        )
                                    )

                                    if image_file:

                                        variant.image.save(
                                            image_file.name,
                                            image_file,
                                            save=True
                                        )

                                except Exception as image_error:

                                    errors.append(
                                        f"Row {row_number}: "
                                        f"Variant image failed - "
                                        f"{image_error}"
                                    )


                            created_variants += 1


                    # =================================
                    # RECALCULATE PRODUCT STOCK
                    # =================================

                    for product in (
                        product_cache.values()
                    ):

                        total_stock = sum(
                            variant.stock
                            for variant
                            in product.variants.all()
                        )

                        product.stock = (
                            total_stock
                        )

                        product.is_available = (
                            total_stock > 0
                        )

                        product.save(
                            update_fields=[
                                "stock",
                                "is_available",
                            ]
                        )


                result = {

                    "products":
                        created_products,

                    "variants":
                        created_variants,

                    "updated_variants":
                        updated_variants,
                }


                request.session.pop(
                    "bulk_import_rows",
                    None
                )


            except Exception as e:

                errors.append(
                    f"Import failed: {e}"
                )


    return render(
        request,
        "store/crm_inventory_bulk_import.html",
        {
            "preview": preview,
            "result": result,
            "errors": errors,
        }
    )
def product_detail(request, product_id):

    product = get_object_or_404(
        Product,
        id=product_id,
        is_archived=False,
        is_available=True,
    )

    reviews = (
        product.reviews
        .all()
        .order_by("-created_at")
    )

    average_rating = (
        product.reviews.aggregate(
            average=Avg("rating")
        )["average"]
        or 0
    )

    user_review = None
    is_saved = False
    pets = []

    if request.user.is_authenticated:

        user_review = (
            Review.objects
            .filter(
                product=product,
                user=request.user
            )
            .first()
        )

        is_saved = (
            Wishlist.objects
            .filter(
                user=request.user,
                product=product
            )
            .exists()
        )

        pets = Pet.objects.filter(
            owner=request.user
        )

        # Only show relevant pets
        if product.pet_type in [
            "dog",
            "cat"
        ]:
            pets = pets.filter(
                pet_type=product.pet_type
            )

    feeding_guides = (
        product.feeding_guides
        .all()
        .order_by("min_weight")
    )

    related_filter = Q(category=product.category)
    if product.brand:
        related_filter |= Q(brand__iexact=product.brand)
    related_products = (
        Product.objects.filter(is_available=True, is_archived=False)
        .exclude(pk=product.pk)
        .filter(related_filter)
        .prefetch_related("variants")
        .order_by("-is_featured", "-id")[:8]
    )

    context = {
        "product": product,
        "reviews": reviews,
        "average_rating": average_rating,
        "user_review": user_review,
        "is_saved": is_saved,

        "pets": pets,

        "feeding_guides":
            feeding_guides,
        "related_products": related_products,
    }

    return render(
        request,
        "store/product_detail.html",
        context
    )

@login_required
def add_review(request, product_id):
    product = get_object_or_404(Product, id=product_id, is_archived=False)

    if request.method == "POST":
        rating = int(request.POST.get("rating"))
        comment = request.POST.get("comment")

        if 1 <= rating <= 5:
            Review.objects.update_or_create(
                product=product,
                user=request.user,
                defaults={
                    "rating": rating,
                    "comment": comment,
                }
            )

    return redirect(
        "product_detail",
        product_id=product.id
    )

def search_products(request):
    query = request.GET.get("q", "").strip()

    products = Product.objects.filter(
        is_available=True,
        is_archived=False,
    ).prefetch_related("variants")

    if query:
        products = products.filter(
            name__icontains=query
        )

    return render(
        request,
        "store/search_results.html",
        {
            "products": products,
            "query": query,
        }
    )


VALID_SALE_STATUSES = ("confirmed", "shipped", "delivered")
INVALID_SALE_PAYMENT_STATUSES = ("failed", "refunded")
CATEGORY_SALES_HISTORY_THRESHOLD = 10
CATEGORY_BEST_SELLER_LIMIT = 4

FOOD_CATEGORIES_BY_PAGE = {
    "dog": ("dog_food",),
    "cat": ("cat_food",),
    "bird": ("bird_food",),
}

# Static market-popularity signals. These names were matched against products
# already sold by Boww & Meow; storefront data always comes from Product.
MARKET_BEST_SELLER_NAMES = {
    "dog": (
        "Pedigree Chicken and Vegetables Adult Dog Dry Food",
        "Royal Canin Mini Puppy Dry Dog Food",
        "Farmina N&D Pumpkin Chicken & Pomegranate Adult Dog Food",
        "Orijen Original Dog Dry Food (All Breeds & Ages)",
    ),
    "cat": (
        "Royal Canin Fit 32 Adult Dry Cat Food",
        "Royal Canin Kitten Dry Cat Food",
        "Farmina N&D Prime Chicken & Pomegranate Grain Free Adult Cat Dry Food",
        "Farmina N&D Ocean Herring & Orange Grain Free Adult Cat Dry Food",
    ),
    "medicine": (
        "Bravecto (20-40KG) Dog Tablet",
        "Simparica Trio (20KG to 40KG) Tablet",
        "Drontal Plus Tasty Tablet",
        "Virbac Epiotic Ear Cleanser (Salicylic Acid) for Dogs & Cats",
    ),
    "wellness": (
        "Virbac Nutrich Multi Vitamin Tablets for Dogs and Cats",
        "Virbac Canitone Joint Support for Dogs and Cats (pack of 30 tablets)",
        "Virbac Vitabest Derm Omega 3+6 Syrup for Dogs and Cats (250ml)",
        "Pedigree Dentastix Oral Care for Adult (Medium Breed 10 to 25 kg) Dog Treats",
    ),
    "grooming": (
        "Himalaya Erina Coat Cleanser Shampoo for Dogs and Cats",
        "Virbac Ketochlor Shampoo Antifungal & Antiseptic for Dogs and Cats (200ml)",
        "Virbac Episoothe Oatmeal Shampoo for Dogs & Cats (200ml)",
        "Canopus Pet Wipes",
    ),
    "bird": (
        "Bird Food Budgies",
        "Birds Need Drops",
        "Respocare Avian Drop",
        "Immuncare Exotic Drops",
    ),
}

CATEGORY_COPY = {
    "dog": ("Dogs", "All Dog Products"),
    "cat": ("Cats", "All Cat Products"),
    "medicine": ("Pharmacy", "Pharmacy Products"),
    "wellness": ("Wellness", "Wellness Products"),
    "grooming": ("Grooming", "Grooming Products"),
    "bird": ("Bird Care", "Bird Care Products"),
    "small_pet": ("Small Pets", "Small Pet Products"),
    "farm": ("Farm Animals", "Farm Animal Products"),
    "fish_reptile": ("Fish & Reptiles", "Fish & Reptile Products"),
    "vaccine": ("Vaccination", "Vaccination Products"),
}


def _with_valid_sales(queryset):
    valid_sales = (
        Q(orderitem__order__status__in=VALID_SALE_STATUSES)
        & ~Q(orderitem__order__payment_status__in=INVALID_SALE_PAYMENT_STATUSES)
    )
    return queryset.annotate(
        sold_count=Coalesce(
            Sum("orderitem__quantity", filter=valid_sales),
            Value(0),
            output_field=IntegerField(),
        )
    )


def _category_best_sellers(queryset, page_type):
    """Return four unique, in-stock products without per-product queries."""
    in_stock = queryset.filter(stock__gt=0)
    valid_sales = (
        Q(orderitem__order__status__in=VALID_SALE_STATUSES)
        & ~Q(orderitem__order__payment_status__in=INVALID_SALE_PAYMENT_STATUSES)
    )
    total_sales = in_stock.aggregate(
        total=Coalesce(
            Sum("orderitem__quantity", filter=valid_sales),
            Value(0),
            output_field=IntegerField(),
        )
    )["total"]
    eligible = _with_valid_sales(in_stock)
    market_names = MARKET_BEST_SELLER_NAMES.get(page_type, ())
    market_rank = Case(
        *[
            When(name=name, then=Value(position))
            for position, name in enumerate(market_names)
        ],
        default=Value(9999),
        output_field=IntegerField(),
    )
    eligible = eligible.annotate(market_rank=market_rank)

    if total_sales >= CATEGORY_SALES_HISTORY_THRESHOLD:
        eligible = eligible.order_by(
            "-sold_count", "market_rank", "-is_featured", "-id"
        )
    else:
        eligible = eligible.order_by(
            "market_rank", "-is_featured", "-sold_count", "-id"
        )

    selected = []
    seen_names = set()
    for product in eligible[:40]:
        normalized_name = product.name.strip().casefold()
        if normalized_name in seen_names:
            continue
        seen_names.add(normalized_name)
        selected.append(product)
        if len(selected) == CATEGORY_BEST_SELLER_LIMIT:
            break
    return selected

def _category_products_page(
    request,
    *,
    page_title,
    page_type,
    category=None,
    category_prefix=None,
    categories=None,
    pet_types=None,
    fixed_product_type=None,
):

    products = Product.objects.filter(
        is_available=True,
        is_archived=False,
    ).prefetch_related("variants")


    # ==========================================
    # CATEGORY FILTER
    # ==========================================

    if category:

        products = products.filter(
            category=category
        )


    elif category_prefix and pet_types:
        products = products.filter(
            Q(category__startswith=category_prefix) | Q(pet_type__in=pet_types)
        )

    elif category_prefix:

        products = products.filter(
            category__startswith=category_prefix
        )


    elif categories and pet_types:
        products = products.filter(
            Q(category__in=categories) | Q(pet_type__in=pet_types)
        )

    elif categories:

        products = products.filter(
            category__in=categories
        )

    elif pet_types:
        products = products.filter(pet_type__in=pet_types)

    if fixed_product_type:
        products = products.filter(product_type=fixed_product_type)


    # ==========================================
    # BEST SELLER DATA
    # ==========================================

    category_products = products
    category_product_count = category_products.count()
    best_sellers = _category_best_sellers(category_products, page_type)
    best_seller_ids = [product.id for product in best_sellers]
    products = _with_valid_sales(category_products)


    # ==========================================
    # SEARCH
    # ==========================================

    query = request.GET.get(
        "q",
        ""
    ).strip()


    if query:

        products = products.filter(

            Q(
                name__icontains=query
            )

            |

            Q(
                brand__icontains=query
            )

            |

            Q(
                flavour__icontains=query
            )

            |

            Q(
                description__icontains=query
            )

            |

            Q(
                supplier_product_id__icontains=query
            )

        )

    product_type = request.GET.get("product_type", "").strip()
    care_area = request.GET.get("care_area", "").strip()
    brand = request.GET.get("brand", "").strip()

    if product_type and not fixed_product_type:
        food_categories = FOOD_CATEGORIES_BY_PAGE.get(page_type)
        if product_type == "food" and food_categories:
            products = products.filter(category__in=food_categories)
        else:
            products = products.filter(product_type=product_type)
    if care_area:
        products = products.filter(care_area=care_area)
    if brand:
        products = products.annotate(
            normalized_brand=Lower(Trim("brand"))
        ).filter(normalized_brand=brand.casefold())

    # On an unfiltered catalogue the top four are already visible immediately
    # above, so omit them from the first catalogue page. During filtering they
    # must remain eligible or valid search results would silently disappear.
    if not any((query, product_type, care_area, brand)):
        products = products.exclude(id__in=best_seller_ids)


    # ==========================================
    # SORT
    # ==========================================

    sort = request.GET.get(
        "sort",
        "featured"
    )


    available_variant_price = ProductVariant.objects.filter(
        product_id=OuterRef("pk"),
        is_available=True,
        stock__gt=0,
    ).order_by("price", "id").values("price")[:1]
    products = products.annotate(
        effective_price=Coalesce(
            Subquery(available_variant_price, output_field=DecimalField()),
            F("price"),
            output_field=DecimalField(max_digits=10, decimal_places=2),
        )
    )

    if sort == "price_low":

        products = products.order_by(
            "effective_price",
            "name",
            "id",
        )


    elif sort == "price_high":

        products = products.order_by(
            "-effective_price",
            "name",
            "id",
        )


    elif sort == "name":

        products = products.order_by(
            "name"
        )


    else:

        # Best sellers first
        # Then featured products
        # Then newest products

        products = products.order_by(
            "-sold_count",
            "-is_featured",
            "-id"
        )


    product_count = category_product_count
    paginator = Paginator(products, 48)
    page_obj = paginator.get_page(request.GET.get("page"))
    filter_params = request.GET.copy()
    filter_params.pop("page", None)

    context = {

        "products":
            page_obj,

        "page_title":
            page_title,

        "page_type":
            page_type,

        "category_heading": CATEGORY_COPY.get(page_type, (page_title, page_title))[0],
        "all_products_heading": CATEGORY_COPY.get(page_type, (page_title, f"All {page_title}"))[1],
        "best_sellers": best_sellers,

        "product_count":
            product_count,

        "page_obj": page_obj,
        "filter_query": filter_params.urlencode(),

        "query":
            query,

        "sort":
            sort,

        "product_type_filter": product_type,
        "care_area_filter": care_area,
        "brand_filter": brand,
        "active_filter_count": sum((
            bool(query),
            bool(product_type),
            bool(care_area),
            bool(brand),
            sort != "featured",
        )),
        "product_types": Product.PRODUCT_TYPE_CHOICES,
        "care_areas": Product.CARE_AREA_CHOICES,
        "available_brands": Product.objects.filter(
            is_available=True,
            is_archived=False,
        ).exclude(brand="").values_list(
            "brand", flat=True
        ).distinct().order_by("brand"),
    }


    return render(
        request,
        "store/category_products.html",
        context,
    )
def dog_products(request):

    return _category_products_page(

        request,

        category_prefix="dog_",
        pet_types=["dog", "both"],

        page_title="Dog Food & Essentials",

        page_type="dog",
    )


def cat_products(request):

    return _category_products_page(

        request,

        category_prefix="cat_",
        pet_types=["cat", "both"],

        page_title="Cat Food & Essentials",

        page_type="cat",
    )

def medicine_products(request):

    return _category_products_page(

        request,

        categories=[
            "medicine",
            "parasite_control",
            "heart_care",
            "kidney_care",
            "respiratory_care",
        ],

        page_title="Veterinary Pharmacy",

        page_type="medicine",
    )


def wellness_products(request):
    return _category_products_page(
        request,
        categories=[
            "supplement",
            "skin_coat",
            "dental",
            "joint_care",
            "digestive",
        ],
        page_title="Health & Supplements",
        page_type="wellness",
    )


def grooming_products(request):
    return _category_products_page(
        request,
        categories=[
            "dog_grooming",
            "cat_grooming",
            "grooming_shampoo",
            "hygiene",
            "training_pads",
            "dental",
        ],
        page_title="Grooming & Hygiene",
        page_type="grooming",
    )


def bird_products(request):
    return _category_products_page(
        request,
        categories=[
            "bird_food",
            "bird_supplement",
            "bird_health",
            "exotic_health",
        ],
        pet_types=["bird"],
        page_title="Bird & Exotic Pet Care",
        page_type="bird",
    )


def small_pet_products(request):
    return _category_products_page(request, pet_types=["small_pet", "exotic"], page_title="Small Pet Care", page_type="small_pet")


def farm_animal_products(request):
    return _category_products_page(request, pet_types=["farm"], page_title="Farm Animal Care", page_type="farm")


def fish_reptile_products(request):
    return _category_products_page(request, pet_types=["fish_reptile"], page_title="Fish & Reptile Care", page_type="fish_reptile")


def vaccination_products(request):
    return _category_products_page(request, fixed_product_type="vaccine", page_title="Vaccination", page_type="vaccine")


def _trust_page(request, page_key):
    return render(request, "store/trust_pages.html", {"page_key": page_key})


def contact_page(request):
    return _trust_page(request, "contact")


def faq_page(request):
    return _trust_page(request, "faq")


def shipping_policy(request):
    return _trust_page(request, "shipping")


def returns_policy(request):
    return _trust_page(request, "returns")


def veterinary_disclaimer(request):
    return _trust_page(request, "veterinary")


def privacy_policy(request):
    return _trust_page(request, "privacy")


def terms_page(request):
    return _trust_page(request, "terms")
@login_required
def wishlist(request):
    items = Wishlist.objects.filter(
        user=request.user,
        product__is_archived=False,
        product__is_available=True,
    ).select_related("product").prefetch_related("product__variants").order_by("-created_at")

    return render(
        request,
        "store/wishlist.html",
        {"items": items}
    )


@login_required
@require_POST
def toggle_wishlist(request, product_id):
    product = get_object_or_404(Product, id=product_id, is_archived=False, is_available=True)

    wishlist_item = Wishlist.objects.filter(
        user=request.user,
        product=product
    ).first()

    if wishlist_item:
        wishlist_item.delete()
    else:
        Wishlist.objects.create(
            user=request.user,
            product=product
        )

    return redirect(
        "product_detail",
        product_id=product.id
    )

@login_required
def my_addresses(request):

    addresses = Address.objects.filter(
        user=request.user
    )

    return render(
        request,
        "store/my_addresses.html",
        {
            "addresses": addresses
        }
    )
@login_required
def add_address(request):

    if request.method == "POST":

        is_default = (
            request.POST.get("is_default") == "on"
        )

        if is_default:
            Address.objects.filter(
                user=request.user
            ).update(is_default=False)
        phone = request.POST.get("phone", "").strip()
        pincode = request.POST.get("pincode", "").strip()

        if not re.fullmatch(r"[6-9]\d{9}", phone):
            return render(
                request,
                "store/add_address.html",
                {
                    "error": "Enter a valid 10-digit Indian mobile number."
                }
            )

        if not re.fullmatch(r"\d{6}", pincode):
            return render(
                request,
                "store/add_address.html",
                {
                    "error": "Enter a valid 6-digit PIN code."
                }
            )
        Address.objects.create(
            user=request.user,
            full_name=request.POST.get("full_name"),
            phone=phone,
            address_line1=request.POST.get("address_line1"),
            address_line2=request.POST.get("address_line2"),
            city=request.POST.get("city"),
            state=request.POST.get("state"),
            pincode=pincode,
            is_default=is_default
        )

        return redirect("my_addresses")

    return render(
        request,
        "store/add_address.html"
    )

@login_required
def edit_address(request, address_id):
    address = get_object_or_404(Address, id=address_id, user=request.user)

    if request.method == "POST":
        phone = request.POST.get("phone", "").strip()
        pincode = request.POST.get("pincode", "").strip()

        if not re.fullmatch(r"[6-9]\d{9}", phone):
            return render(request, "store/edit_address.html", {
                "address": address,
                "error": "Enter a valid 10-digit Indian mobile number."
            })

        if not re.fullmatch(r"\d{6}", pincode):
            return render(request, "store/edit_address.html", {
                "address": address,
                "error": "Enter a valid 6-digit PIN code."
            })

        address.full_name = request.POST.get("full_name")
        address.phone = phone
        address.address_line1 = request.POST.get("address_line1")
        address.address_line2 = request.POST.get("address_line2")
        address.city = request.POST.get("city")
        address.state = request.POST.get("state")
        address.pincode = pincode

        is_default = request.POST.get("is_default") == "on"
        if is_default:
            Address.objects.filter(user=request.user).exclude(id=address.id).update(is_default=False)

        address.is_default = is_default
        address.save()
        return redirect("my_addresses")

    return render(request, "store/edit_address.html", {"address": address})

@login_required
@require_POST
def delete_address(request, address_id):
    address = get_object_or_404(
        Address,
        id=address_id,
        user=request.user
    )

    address.delete()

    return redirect("my_addresses")


def verify_payment(request):
    razorpay_payment_id = request.GET.get("razorpay_payment_id")
    razorpay_order_id = request.GET.get("razorpay_order_id")
    razorpay_signature = request.GET.get("razorpay_signature")

    order_id = request.session.get("current_order_id")
    saved_razorpay_order_id = request.session.get("razorpay_order_id")

    if not order_id:
        return redirect("home")

    order = get_object_or_404(Order, id=order_id)

    if saved_razorpay_order_id != razorpay_order_id:
        _restore_order_inventory(order)
        order.payment_status = "failed"
        order.save(update_fields=["payment_status"])
        return render(request, "store/payment_failed.html", {"order": order})

    client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))

    try:
        client.utility.verify_payment_signature({
            "razorpay_order_id": razorpay_order_id,
            "razorpay_payment_id": razorpay_payment_id,
            "razorpay_signature": razorpay_signature,
        })

        if order.payment_status != "paid":
            with transaction.atomic():
                locked_order = Order.objects.select_for_update().get(id=order.id)
                if not locked_order.inventory_reserved:
                    raise ValueError("This order no longer has reserved inventory.")
                locked_order.payment_status = "paid"
                locked_order.status = "confirmed"
                locked_order.save(update_fields=["payment_status", "status"])

            send_order_confirmation(order)

        request.session["cart"] = {}
        request.session.pop("current_order_id", None)
        request.session.pop("razorpay_order_id", None)
        return redirect("order_success", order_id=order.id)

    except (razorpay.errors.SignatureVerificationError, ValueError):
        _restore_order_inventory(order)
        order.payment_status = "failed"
        order.save(update_fields=["payment_status"])
        return render(request, "store/payment_failed.html", {"order": order})

@require_POST
def retry_payment(request, order_id):
    order = get_object_or_404(Order, id=order_id)
    if not _request_can_access_order(request, order):
        return redirect("home")

    if order.payment_status == "paid":
        return redirect(
            "order_success",
            order_id=order.id
        )

    try:
        _reserve_order_inventory(order)
    except ValueError:
        return render(request, "store/payment_failed.html", {
            "order": order,
            "error": "One or more items are no longer available in the requested quantity.",
        })

    client = razorpay.Client(
        auth=(
            settings.RAZORPAY_KEY_ID,
            settings.RAZORPAY_KEY_SECRET
        )
    )

    amount_in_paise = int(order.total_amount * 100)

    try:
        razorpay_order = client.order.create({
            "amount": amount_in_paise,
            "currency": "INR",
            "receipt": f"retry_bows_meows_{order.id}",
            "payment_capture": 1,
        })
    except Exception:
        _restore_order_inventory(order)
        order.payment_status = "failed"
        order.save(update_fields=["payment_status"])
        return render(request, "store/payment_failed.html", {
            "order": order,
            "error": "We couldn't restart the payment. Please try again.",
        })

    order.payment_status = "pending"
    order.save(update_fields=["payment_status"])

    request.session["current_order_id"] = order.id
    request.session["razorpay_order_id"] = razorpay_order["id"]

    return render(
        request,
        "store/payment.html",
        {
            "order": order,
            "razorpay_order_id": razorpay_order["id"],
            "razorpay_key_id": settings.RAZORPAY_KEY_ID,
            "amount": amount_in_paise,
        }
    )
@require_POST
def payment_failed_view(request, order_id):
    order = get_object_or_404(Order, id=order_id)
    if not _request_can_access_order(request, order):
        return redirect("home")

    if order.payment_status != "paid":
        _restore_order_inventory(order)
        order.payment_status = "failed"
        order.save(update_fields=["payment_status"])

    return render(
        request,
        "store/payment_failed.html",
        {"order": order}
    )


@require_POST
def payment_cancelled(request, order_id):
    order = get_object_or_404(Order, id=order_id)
    if not _request_can_access_order(request, order):
        return redirect("home")

    if order.payment_status != "paid":
        _restore_order_inventory(order)
        order.payment_status = "failed"
        order.save(update_fields=["payment_status"])

    return render(
        request,
        "store/payment_cancelled.html",
        {"order": order}
    )

@login_required
def crm_bulk_images(request):

    if not request.user.is_staff:
        return redirect("home")

    products = (
        Product.objects
        .prefetch_related(
            "variants",
            "gallery_images"
        )
        .order_by(
            "brand",
            "name"
        )
    )

    query = request.GET.get(
        "q",
        ""
    ).strip()

    brand = request.GET.get(
        "brand",
        ""
    ).strip()

    missing_only = (
        request.GET.get(
            "missing"
        )
        == "1"
    )


    if query:

        products = products.filter(

            Q(
                name__icontains=query
            )

            |

            Q(
                brand__icontains=query
            )
        )


    if brand:

        products = products.filter(
            brand=brand
        )


    if missing_only:

        products = products.filter(
            image__isnull=True
        )


    brands = (
        Product.objects
        .exclude(
            brand=""
        )
        .values_list(
            "brand",
            flat=True
        )
        .distinct()
        .order_by(
            "brand"
        )
    )


    if request.method == "POST":

        action = request.POST.get(
            "action"
        )

        if action == "batch_upload":
            uploads = request.FILES.getlist("batch_images")
            replace_existing = request.POST.get("replace_existing") == "on"
            imported = 0
            skipped = 0
            unmatched = []

            for upload in uploads:
                try:
                    _validate_uploaded_product_image(upload)
                    stem = os.path.splitext(os.path.basename(upload.name))[0]
                    product_match = re.fullmatch(
                        r"(\d+)-(main|ingredients|nutrition|feeding)",
                        stem,
                        flags=re.IGNORECASE,
                    )

                    if product_match:
                        product_id = int(product_match.group(1))
                        image_type = product_match.group(2).lower()
                        product = Product.objects.filter(id=product_id).first()
                        if not product:
                            unmatched.append(upload.name)
                            continue
                        if image_type == "main":
                            if product.image and not replace_existing:
                                skipped += 1
                                continue
                            if product.image:
                                product.image.delete(save=False)
                            product.image.save(upload.name, upload, save=True)
                        else:
                            existing = ProductImage.objects.filter(
                                product=product,
                                image_type=image_type,
                            ).first()
                            if existing and not replace_existing:
                                skipped += 1
                                continue
                            if existing:
                                existing.image.delete(save=False)
                                existing.image.save(upload.name, upload, save=True)
                            else:
                                ProductImage.objects.create(
                                    product=product,
                                    image=upload,
                                    image_type=image_type,
                                    sort_order={"ingredients": 1, "nutrition": 2, "feeding": 3}[image_type],
                                )
                        imported += 1
                        continue

                    variant = ProductVariant.objects.filter(
                        sku__iexact=stem
                    ).first()
                    if not variant:
                        unmatched.append(upload.name)
                        continue
                    if variant.image and not replace_existing:
                        skipped += 1
                        continue
                    if variant.image:
                        variant.image.delete(save=False)
                    variant.image.save(upload.name, upload, save=True)
                    imported += 1
                except ValueError as exc:
                    unmatched.append(f"{upload.name} ({exc})")

            if imported:
                messages.success(request, f"Imported {imported} image(s) successfully.")
            if skipped:
                messages.warning(request, f"Skipped {skipped} existing image(s). Enable replacement to overwrite them.")
            if unmatched:
                preview = ", ".join(unmatched[:8])
                suffix = " …" if len(unmatched) > 8 else ""
                messages.error(request, f"Could not match {len(unmatched)} file(s): {preview}{suffix}")
            if not uploads:
                messages.warning(request, "Choose one or more image files first.")
            return redirect("crm_bulk_images")


        # ==============================
        # REMOVE IMAGE
        # ==============================

        if action == "remove":

            image_kind = request.POST.get(
                "image_kind"
            )

            object_id = request.POST.get(
                "object_id"
            )


            if image_kind == "main":

                product = get_object_or_404(
                    Product,
                    id=object_id
                )

                if product.image:
                    product.image.delete(
                        save=False
                    )

                product.image = None

                product.save(
                    update_fields=[
                        "image"
                    ]
                )


            elif image_kind == "gallery":

                gallery_image = (
                    get_object_or_404(
                        ProductImage,
                        id=object_id
                    )
                )

                gallery_image.image.delete(
                    save=False
                )

                gallery_image.delete()


            return redirect(
                request.path
            )


        # ==============================
        # SAVE / REPLACE IMAGES
        # ==============================

        for product in products:

            # MAIN IMAGE

            main_url = (
                request.POST.get(
                    f"main_image_{product.id}",
                    ""
                ).strip()
            )
            main_upload = request.FILES.get(
                f"main_upload_{product.id}"
            )


            if main_upload or main_url:

                try:

                    image_file = main_upload or download_product_image(
                        main_url,
                        prefix=f"product-{product.id}"
                    )

                    if image_file:

                        if product.image:
                            product.image.delete(
                                save=False
                            )

                        product.image.save(
                            image_file.name,
                            image_file,
                            save=True
                        )

                except Exception as e:

                    print(
                        "MAIN IMAGE ERROR:",
                        product.id,
                        e
                    )


            # =================================
            # GALLERY IMAGE TYPES
            # =================================

            image_types = [
                "ingredients",
                "nutrition",
                "feeding",
            ]


            for image_type in image_types:

                image_url = (
                    request.POST.get(
                        f"{image_type}_image_{product.id}",
                        ""
                    ).strip()
                )
                image_upload = request.FILES.get(
                    f"{image_type}_upload_{product.id}"
                )


                if not image_upload and not image_url:
                    continue


                try:

                    image_file = image_upload or download_product_image(
                        image_url,
                        prefix=f"{product.id}-{image_type}"
                    )


                    if not image_file:
                        continue


                    existing = (
                        ProductImage.objects
                        .filter(
                            product=product,
                            image_type=image_type
                        )
                        .first()
                    )


                    if existing:

                        if existing.image:

                            existing.image.delete(
                                save=False
                            )

                        existing.image.save(
                            image_file.name,
                            image_file,
                            save=True
                        )


                    else:

                        ProductImage.objects.create(

                            product=product,

                            image=image_file,

                            image_type=image_type,

                            sort_order={
                                "ingredients": 1,
                                "nutrition": 2,
                                "feeding": 3,
                            }.get(
                                image_type,
                                10
                            ),
                        )


                except Exception as e:

                    print(
                        "GALLERY IMAGE ERROR:",
                        product.id,
                        image_type,
                        e
                    )


        return redirect(
            "crm_bulk_images"
        )


    product_rows = []


    for product in products:

        gallery_map = {

            image.image_type: image

            for image
            in product.gallery_images.all()

        }


        image_count = 0


        if product.image:
            image_count += 1


        for image_type in [
            "ingredients",
            "nutrition",
            "feeding",
        ]:

            if image_type in gallery_map:
                image_count += 1


        product_rows.append({

            "product":
                product,

            "ingredients_image":
                gallery_map.get(
                    "ingredients"
                ),

            "nutrition_image":
                gallery_map.get(
                    "nutrition"
                ),

            "feeding_image":
                gallery_map.get(
                    "feeding"
                ),

            "image_count":
                image_count,
        })


    context = {

        "product_rows":
            product_rows,

        "brands":
            brands,

        "query":
            query,

        "selected_brand":
            brand,

        "missing_only":
            missing_only,
    }


    return render(
        request,
        "store/crm_bulk_images.html",
        context
    )
