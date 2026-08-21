from django.shortcuts import render, redirect, get_object_or_404
from .models import Product, ProductVariant, Order, OrderItem
from django.contrib.auth.models import User
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from .models import Product, Order, OrderItem, Pet
from django.contrib.auth.models import User
from django.db.models import Sum
from django.db.models import Sum, Count
from django.db.models import Sum, Count, F, DecimalField, ExpressionWrapper
from django.db.models.functions import TruncDate
from datetime import timedelta
from django.utils import timezone
from django.db.models import Avg
from .models import Product, Order, OrderItem, Pet, Review
from .models import Product, Order, OrderItem, Pet, Review, Wishlist
from .models import Address
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
from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.core.mail import EmailMultiAlternatives
from brevo.core.api_error import ApiError
from .models import (
    Product,
    ProductVariant,
    FeedingGuide,
    Order,
    OrderItem,
)
def home(request):
    products = Product.objects.filter(is_available=True)

    return render(
        request,
        "store/home.html",
        {"products": products}
    )

def send_brevo_email(to_email, to_name, subject, html_content):

    api_key = os.getenv("BREVO_API_KEY")
    sender_email = os.getenv("BREVO_SENDER_EMAIL")
    sender_name = os.getenv("BREVO_SENDER_NAME", "Bows & Meows")

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
        if not product:
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


def add_to_cart(request, product_id):
    product = get_object_or_404(Product, id=product_id, is_available=True)
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

    replace_key = request.GET.get("replace")
    if replace_key and replace_key != line_key and replace_key in cart:
        del cart[replace_key]

    request.session["cart"] = cart
    request.session.modified = True
    return redirect("cart")


def cart(request):
    cart_items, total = _build_cart_items(request)
    return render(request, "store/cart.html", {"cart_items": cart_items, "total": total})


def remove_from_cart(request, product_id):
    cart = _normalize_cart(request)
    variant_id = request.GET.get("variant")
    cart.pop(_cart_line_key(product_id, variant_id), None)
    request.session["cart"] = cart
    request.session.modified = True
    return redirect("cart")


def increase_quantity(request, product_id):
    cart = _normalize_cart(request)
    variant_id = request.GET.get("variant")
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


def decrease_quantity(request, product_id):
    cart = _normalize_cart(request)
    variant_id = request.GET.get("variant")
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
        f"Bows & Meows - Order #{order.id} Confirmed"
    )

    html_content = render_to_string(
        "store/emails/order_confirmation.html",
        {
            "order": order
        }
    )

    text_content = (
        f"Hi {order.customer_name},\n\n"
        f"Thank you for shopping with Bows & Meows!\n\n"
        f"Order #{order.id}\n"
        f"Total: ₹{order.total_amount}\n"
        f"Payment: {order.get_payment_method_display()}\n"
        f"Delivery Address: {order.address}\n\n"
        f"Thank you,\n"
        f"Bows & Meows"
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
        f"Bows & Meows"
    )

    send_brevo_email(
        to_email=order.email,
        to_name=order.customer_name,
        subject=subject,
        html_content=html_content,
    )

def checkout(request):
    cart_items, total = _build_cart_items(request)
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
                if item["quantity"] > fresh.stock:
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
            )

            for item in cart_items:
                OrderItem.objects.create(
                    order=order,
                    product=item["product"],
                    variant=item["variant"],
                    variant_size=item["variant"].size if item["variant"] else "",
                    quantity=item["quantity"],
                    price=item["unit_price"],
                )

            if payment_method == "cod":
                affected = set()
                for item in cart_items:
                    if item["variant"]:
                        variant = ProductVariant.objects.select_for_update().get(
                            id=item["variant"].id, product=item["product"]
                        )
                        if item["quantity"] > variant.stock:
                            raise ValueError(f"Not enough stock for {item['product'].name} {variant.size}")
                        variant.stock -= item["quantity"]
                        if variant.stock <= 0:
                            variant.stock = 0
                            variant.is_available = False
                        variant.save()
                        affected.add(item["product"].id)
                    else:
                        product = Product.objects.select_for_update().get(id=item["product"].id)
                        if item["quantity"] > product.stock:
                            raise ValueError(f"Not enough stock for {product.name}")
                        product.stock -= item["quantity"]
                        if product.stock <= 0:
                            product.stock = 0
                            product.is_available = False
                        product.save()

                for pid in affected:
                    _sync_product_stock(Product.objects.get(id=pid))

        request.session.pop("checkout_token", None)

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
                order.payment_status = "failed"
                order.save()
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
        "total": total,
        "default_address": default_address,
        "addresses": addresses,
        "checkout_token": checkout_token,
    })

def order_success(request, order_id):
    order = get_object_or_404(Order, id=order_id)

    return render(
        request,
        "store/order_success.html",
        {"order": order}
    )

def register_view(request):

    if request.method == "POST":

        username = request.POST.get("username")
        email = request.POST.get("email")
        password = request.POST.get("password")

        if User.objects.filter(
            username=username
        ).exists():

            return render(
                request,
                "store/register.html",
                {
                    "error":
                    "Username already exists"
                }
            )

        if User.objects.filter(email__iexact=email).exists():
            return render(
                request,
                "store/register.html",
                {"error": "An account with this email already exists."}
                )

        user = User.objects.create_user(
                        username=username,
                        email=email,
                        password=password
                    )

        login(request, user)

        return redirect("home")

    return render(
        request,
        "store/register.html"
    )

def login_view(request):
    if request.method == "POST":
        username = request.POST.get("username")
        password = request.POST.get("password")

        user = authenticate(
            request,
            username=username,
            password=password
        )

        if user is not None:
            login(request, user)

            next_url = request.GET.get("next")

            if next_url:
                return redirect(next_url)

            return redirect("home")

        return render(
            request,
            "store/login.html",
            {"error": "Invalid username or password"}
        )

    return render(request, "store/login.html")


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
        Pet.objects.create(
            owner=request.user,
            name=request.POST.get("name"),
            pet_type=request.POST.get("pet_type"),
            breed=request.POST.get("breed"),
            age=request.POST.get("age") or None,
            weight=request.POST.get("weight") or None,
            notes=request.POST.get("notes")
        )

        return redirect("my_pets")

    return render(request, "store/add_pet.html")

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
        product.category = request.POST.get("category")
        product.life_stage = request.POST.get("life_stage", "")
        product.flavour = request.POST.get("flavour", "").strip()
        product.key_benefits = request.POST.get("key_benefits", "").strip()
        product.price = request.POST.get("price")
        product.original_price = request.POST.get("original_price") or None
        product.stock = request.POST.get("stock") or 0
        product.description = request.POST.get("description", "").strip()
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
        affected = set()
        with transaction.atomic():
            for item in order.items.all():
                if item.variant_id:
                    variant = ProductVariant.objects.select_for_update().filter(id=item.variant_id).first()
                    if variant:
                        variant.stock += item.quantity
                        variant.is_available = True
                        variant.save()
                        affected.add(item.product_id)
                else:
                    product = Product.objects.select_for_update().get(id=item.product_id)
                    product.stock += item.quantity
                    product.is_available = True
                    product.save()
            for pid in affected:
                _sync_product_stock(Product.objects.get(id=pid))

    elif old_status == "cancelled" and new_status != "cancelled":
        for item in order.items.all():
            if item.variant_id:
                variant = ProductVariant.objects.filter(id=item.variant_id).first()
                if not variant or variant.stock < item.quantity:
                    return redirect("crm_orders")
            elif item.product.stock < item.quantity:
                return redirect("crm_orders")

        affected = set()
        with transaction.atomic():
            for item in order.items.all():
                if item.variant_id:
                    variant = ProductVariant.objects.select_for_update().get(id=item.variant_id)
                    variant.stock -= item.quantity
                    if variant.stock <= 0:
                        variant.stock = 0
                        variant.is_available = False
                    variant.save()
                    affected.add(item.product_id)
                else:
                    product = Product.objects.select_for_update().get(id=item.product_id)
                    product.stock -= item.quantity
                    if product.stock <= 0:
                        product.stock = 0
                        product.is_available = False
                    product.save()
            for pid in affected:
                _sync_product_stock(Product.objects.get(id=pid))

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


            variant_image = request.FILES.get(
                f"variant_image_{i}"
            )
            variant = ProductVariant.objects.create(

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

                stock=(
                    row.get(
                        "variant_stock"
                    )
                    or 0
                ),

                sku=sku,

                is_available=(
                    int(
                        row.get(
                            "variant_stock"
                        )
                        or 0
                    ) > 0
                ),
            )
            if variant_image_url:

                try:

                    downloaded_variant_image = (
                        download_product_image(
                            variant_image_url,
                            prefix=sku
                        )
                    )

                    if downloaded_variant_image:

                        variant.image.save(
                            downloaded_variant_image.name,
                            downloaded_variant_image,
                            save=True
                        )

                except Exception as image_error:

                    errors.append(
                        f"Row {row_number}: "
                        f"Variant image failed - "
                        f"{image_error}"
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


        return redirect(
            "crm_inventory"
        )


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


    filename = (
        f"{prefix}-"
        f"{uuid.uuid4().hex[:12]}"
        f"{extension}"
    )


    return ContentFile(
        response.content,
        name=filename
    )
@login_required
def crm_inventory_bulk_import(request):

    if not request.user.is_staff:
        return redirect("home")

    result = None
    errors = []

    if request.method == "POST":

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

                created_products = 0
                created_variants = 0
                updated_products = 0

                product_cache = {}


                with transaction.atomic():

                    for row_number, row in enumerate(
                        reader,
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


                        if not name:

                            errors.append(
                                f"Row {row_number}: "
                                "Product name is missing."
                            )

                            continue


                        if not product_code:

                            errors.append(
                                f"Row {row_number}: "
                                "Product code is missing."
                            )

                            continue


                        if not size:

                            errors.append(
                                f"Row {row_number}: "
                                "Variant size is missing."
                            )

                            continue


                        if not sku:

                            errors.append(
                                f"Row {row_number}: "
                                "SKU is missing."
                            )

                            continue


                        # =================================
                        # GET / CREATE PRODUCT
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
                                    brand=row.get(
                                        "brand",
                                        ""
                                    ).strip()
                                )
                                .first()
                            )


                        if product:

                            updated_products += 1

                        else:

                            product = Product.objects.create(

                                name=name,

                                brand=row.get(
                                    "brand",
                                    ""
                                ).strip(),

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

                                key_benefits=row.get(
                                    "key_benefits",
                                    ""
                                ).replace(
                                    " | ",
                                    "\n"
                                ),

                                price=(
                                    row.get("base_price")
                                    or 0
                                ),

                                original_price=(
                                    row.get("base_mrp")
                                    or None
                                ),

                                stock=0,

                                is_featured=(
                                    row.get(
                                        "featured",
                                        ""
                                    ).lower()
                                    in ["yes", "true", "1"]
                                ),

                                is_available=(
                                    row.get(
                                        "available",
                                        "yes"
                                    ).lower()
                                    in ["yes", "true", "1"]
                                ),
                            )

                            created_products += 1


                        # ==========================================
                        # PRODUCT IMAGE
                        # ==========================================

                        if (
                            product_image_url
                            and not product.image
                        ):

                            try:

                                downloaded_image = (
                                    download_product_image(
                                        product_image_url,
                                        prefix=product_code
                                    )
                                )

                                if downloaded_image:

                                    product.image.save(
                                        downloaded_image.name,
                                        downloaded_image,
                                        save=True
                                    )

                            except Exception as image_error:

                                errors.append(
                                    f"Row {row_number}: "
                                    f"Product image failed - "
                                    f"{image_error}"
                                )


                        # KEEP THIS AFTER THE IMAGE CODE
                        product_cache[
                            product_code
                        ] = product

                        # =================================
                        # VARIANT
                        # =================================

                        existing_variant = (
                            ProductVariant.objects
                            .filter(
                                sku=sku
                            )
                            .first()
                        )


                        if existing_variant:

                            existing_variant.size = (
                                size
                            )

                            existing_variant.price = (
                                row.get(
                                    "variant_price"
                                )
                                or 0
                            )

                            existing_variant.original_price = (
                                row.get(
                                    "variant_mrp"
                                )
                                or None
                            )

                            existing_variant.stock = (
                                row.get(
                                    "variant_stock"
                                )
                                or 0
                            )

                            existing_variant.is_available = (
                                int(
                                    existing_variant.stock
                                ) > 0
                            )
                            if variant_image_url:

                                try:

                                    downloaded_variant_image = (
                                        download_product_image(
                                            variant_image_url,
                                            prefix=sku
                                        )
                                    )

                                    if downloaded_variant_image:

                                        existing_variant.image.save(
                                            downloaded_variant_image.name,
                                            downloaded_variant_image,
                                            save=False
                                        )

                                except Exception as image_error:

                                    errors.append(
                                        f"Row {row_number}: "
                                        f"Variant image failed - "
                                        f"{image_error}"
                                    )
                            existing_variant.save()


                        else:

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

                                stock=(
                                    row.get(
                                        "variant_stock"
                                    )
                                    or 0
                                ),

                                sku=sku,

                                is_available=(
                                    int(
                                        row.get(
                                            "variant_stock"
                                        )
                                        or 0
                                    ) > 0
                                ),
                            )

                            created_variants += 1


                    # =================================
                    # RECALCULATE TOTAL PRODUCT STOCK
                    # =================================

                    for product in product_cache.values():

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
                                "is_available"
                            ]
                        )


                result = {
                    "products":
                        created_products,

                    "variants":
                        created_variants,

                    "updated_products":
                        updated_products,
                }


            except Exception as e:

                errors.append(
                    f"Import failed: {e}"
                )


    return render(
        request,
        "store/crm_inventory_bulk_import.html",
        {
            "result": result,
            "errors": errors,
        }
    )
def product_detail(request, product_id):

    product = get_object_or_404(
        Product,
        id=product_id
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

    context = {
        "product": product,
        "reviews": reviews,
        "average_rating": average_rating,
        "user_review": user_review,
        "is_saved": is_saved,

        "pets": pets,

        "feeding_guides":
            feeding_guides,
    }

    return render(
        request,
        "store/product_detail.html",
        context
    )

@login_required
def add_review(request, product_id):
    product = get_object_or_404(Product, id=product_id)

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
        is_available=True
    )

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

def _category_products_page(request, *, page_title, page_type, category_prefix=None, categories=None):
    products = Product.objects.filter(is_available=True)

    if category_prefix:
        products = products.filter(category__startswith=category_prefix)
    if categories:
        products = products.filter(category__in=categories)

    query = request.GET.get("q", "").strip()
    sort = request.GET.get("sort", "featured")

    if query:
        products = products.filter(name__icontains=query)

    if sort == "price_low":
        products = products.order_by("price", "name")
    elif sort == "price_high":
        products = products.order_by("-price", "name")
    elif sort == "name":
        products = products.order_by("name")
    else:
        products = products.order_by("-is_featured", "-id")

    return render(request, "store/category_products.html", {
        "products": products,
        "page_title": page_title,
        "page_type": page_type,
        "product_count": products.count(),
        "query": query,
        "sort": sort,
    })


def dog_products(request):
    return _category_products_page(
        request,
        category_prefix="dog_",
        page_title="Dog Food & Essentials",
        page_type="dog",
    )


def cat_products(request):
    return _category_products_page(
        request,
        category_prefix="cat_",
        page_title="Cat Food & Essentials",
        page_type="cat",
    )


def medicine_products(request):
    return _category_products_page(
        request,
        categories=["medicine", "supplement", "skin_coat", "dental", "joint_care", "digestive"],
        page_title="Pet Health & Wellness",
        page_type="medicine",
    )

@login_required
def wishlist(request):
    items = Wishlist.objects.filter(
        user=request.user
    ).select_related("product").order_by("-created_at")

    return render(
        request,
        "store/wishlist.html",
        {"items": items}
    )


@login_required
def toggle_wishlist(request, product_id):
    product = get_object_or_404(Product, id=product_id)

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
        order.payment_status = "failed"
        order.save()
        return render(request, "store/payment_failed.html", {"order": order})

    client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))

    try:
        client.utility.verify_payment_signature({
            "razorpay_order_id": razorpay_order_id,
            "razorpay_payment_id": razorpay_payment_id,
            "razorpay_signature": razorpay_signature,
        })

        if order.payment_status != "paid":
            affected = set()
            with transaction.atomic():
                for item in order.items.select_related("product", "variant").all():
                    if item.variant_id:
                        variant = ProductVariant.objects.select_for_update().get(id=item.variant_id)
                        if item.quantity > variant.stock:
                            raise ValueError(f"Not enough stock for {item.product.name} {item.variant_size}")
                        variant.stock -= item.quantity
                        if variant.stock <= 0:
                            variant.stock = 0
                            variant.is_available = False
                        variant.save()
                        affected.add(item.product_id)
                    else:
                        product = Product.objects.select_for_update().get(id=item.product_id)
                        if item.quantity > product.stock:
                            raise ValueError(f"Not enough stock for {product.name}")
                        product.stock -= item.quantity
                        if product.stock <= 0:
                            product.stock = 0
                            product.is_available = False
                        product.save()

                for pid in affected:
                    _sync_product_stock(Product.objects.get(id=pid))

                order.payment_status = "paid"
                order.status = "confirmed"
                order.save()

            send_order_confirmation(order)

        request.session["cart"] = {}
        request.session.pop("current_order_id", None)
        request.session.pop("razorpay_order_id", None)
        return redirect("order_success", order_id=order.id)

    except (razorpay.errors.SignatureVerificationError, ValueError):
        order.payment_status = "failed"
        order.save()
        return render(request, "store/payment_failed.html", {"order": order})

@login_required
def retry_payment(request, order_id):

    order = get_object_or_404(
        Order,
        id=order_id,
        user=request.user
    )

    if order.payment_status == "paid":
        return redirect(
            "order_success",
            order_id=order.id
        )

    client = razorpay.Client(
        auth=(
            settings.RAZORPAY_KEY_ID,
            settings.RAZORPAY_KEY_SECRET
        )
    )

    amount_in_paise = int(order.total_amount * 100)

    razorpay_order = client.order.create({
        "amount": amount_in_paise,
        "currency": "INR",
        "receipt": f"retry_bows_meows_{order.id}",
        "payment_capture": 1,
    })

    order.payment_status = "pending"
    order.save()

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
@login_required
def payment_failed_view(request, order_id):

    order = get_object_or_404(
        Order,
        id=order_id,
        user=request.user
    )

    if order.payment_status != "paid":
        order.payment_status = "failed"
        order.save()

    return render(
        request,
        "store/payment_failed.html",
        {"order": order}
    )


@login_required
def payment_cancelled(request, order_id):

    order = get_object_or_404(
        Order,
        id=order_id,
        user=request.user
    )

    return render(
        request,
        "store/payment_cancelled.html",
        {"order": order}
    )