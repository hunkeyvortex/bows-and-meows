from django.shortcuts import render, redirect, get_object_or_404
from .models import Product, Order, OrderItem
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
from brevo import Brevo
from brevo.transactional_emails import (
    SendTransacEmailRequestSender,
    SendTransacEmailRequestToItem,
)
from brevo.core.api_error import ApiError
import re
from django.db import transaction
import uuid
from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.core.mail import EmailMultiAlternatives
def home(request):
    products = Product.objects.filter(is_available=True)

    return render(
        request,
        "store/home.html",
        {"products": products}
    )

from brevo.core.api_error import ApiError

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
def add_to_cart(request, product_id):
    product = get_object_or_404(Product, id=product_id)

    cart = request.session.get("cart", {})

    product_id_string = str(product.id)

    if product_id_string in cart:
        cart[product_id_string] += 1
    else:
        cart[product_id_string] = 1

    request.session["cart"] = cart

    return redirect("cart")


def cart(request):
    cart = request.session.get("cart", {})

    cart_items = []
    total = 0

    for product_id, quantity in cart.items():

        product = get_object_or_404(Product, id=product_id)

        subtotal = product.price * quantity

        total += subtotal

        cart_items.append({
            "product": product,
            "quantity": quantity,
            "subtotal": subtotal,
        })

    context = {
        "cart_items": cart_items,
        "total": total,
    }

    return render(request, "store/cart.html", context)


def remove_from_cart(request, product_id):
    cart = request.session.get("cart", {})

    product_id_string = str(product_id)

    if product_id_string in cart:
        del cart[product_id_string]

    request.session["cart"] = cart

    return redirect("cart")
def increase_quantity(request, product_id):
    cart = request.session.get("cart", {})
    product_id_string = str(product_id)

    if product_id_string in cart:
        cart[product_id_string] += 1

    request.session["cart"] = cart

    return redirect("cart")


def decrease_quantity(request, product_id):
    cart = request.session.get("cart", {})
    product_id_string = str(product_id)

    if product_id_string in cart:
        cart[product_id_string] -= 1

        if cart[product_id_string] <= 0:
            del cart[product_id_string]

    request.session["cart"] = cart

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
    cart = request.session.get("cart", {})

    if not cart:
        return redirect("cart")


    # --------------------------------
    # CHECKOUT TOKEN
    # --------------------------------

    checkout_token = request.session.get("checkout_token")

    if not checkout_token:
        checkout_token = str(uuid.uuid4())
        request.session["checkout_token"] = checkout_token


    # --------------------------------
    # BUILD CART
    # --------------------------------

    cart_items = []
    total = 0

    for product_id, quantity in cart.items():

        product = get_object_or_404(
            Product,
            id=product_id
        )

        if quantity > product.stock:
            return redirect("cart")

        subtotal = product.price * quantity
        total += subtotal

        cart_items.append({
            "product": product,
            "quantity": quantity,
            "subtotal": subtotal,
        })


    # --------------------------------
    # SAVED ADDRESSES
    # --------------------------------

    default_address = None
    addresses = []

    if request.user.is_authenticated:

        default_address = Address.objects.filter(
            user=request.user,
            is_default=True
        ).first()

        addresses = Address.objects.filter(
            user=request.user
        ).order_by(
            "-is_default",
            "-created_at"
        )


    # --------------------------------
    # POST / PLACE ORDER
    # --------------------------------

    if request.method == "POST":

        submitted_token = request.POST.get(
            "checkout_token"
        )

        session_token = request.session.get(
            "checkout_token"
        )

        if (
            not submitted_token
            or submitted_token != session_token
        ):
            return redirect("cart")


        # --------------------------------
        # RE-CHECK STOCK
        # --------------------------------

        for item in cart_items:

            fresh_product = Product.objects.get(
                id=item["product"].id
            )

            if item["quantity"] > fresh_product.stock:

                return render(
                    request,
                    "store/checkout.html",
                    {
                        "cart_items": cart_items,
                        "total": total,
                        "default_address": default_address,
                        "addresses": addresses,
                        "checkout_token": checkout_token,
                        "error": (
                            f"Only {fresh_product.stock} unit(s) "
                            f"of {fresh_product.name} are available."
                        ),
                    }
                )


        # --------------------------------
        # ADDRESS
        # --------------------------------

        selected_address_id = request.POST.get(
            "saved_address"
        )

        selected_address = None

        if (
            request.user.is_authenticated
            and selected_address_id
        ):

            selected_address = Address.objects.filter(
                id=selected_address_id,
                user=request.user
            ).first()


        if selected_address:

            customer_name = selected_address.full_name
            phone = selected_address.phone

            address_parts = [
                selected_address.address_line1,
                selected_address.address_line2,
                selected_address.city,
                selected_address.state,
            ]

            address_parts = [
                part
                for part in address_parts
                if part
            ]

            address = ", ".join(address_parts)

            address += f" - {selected_address.pincode}"

        else:

            customer_name = request.POST.get(
                "customer_name"
            )

            phone = request.POST.get(
                "phone"
            )

            address = request.POST.get(
                "address"
            )


        email = request.POST.get("email")

        payment_method = request.POST.get(
            "payment_method"
        )


        # ==================================
        # CREATE LOCAL ORDER SAFELY
        # ==================================

        with transaction.atomic():

            order = Order.objects.create(

                user=(
                    request.user
                    if request.user.is_authenticated
                    else None
                ),

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
                    quantity=item["quantity"],
                    price=item["product"].price,
                )


            # ==================================
            # COD STOCK UPDATE
            # ==================================

            if payment_method == "cod":

                for item in cart_items:

                    product = Product.objects.select_for_update().get(
                        id=item["product"].id
                    )

                    if item["quantity"] > product.stock:
                        raise ValueError(
                            f"Not enough stock for {product.name}"
                        )

                    product.stock -= item["quantity"]

                    if product.stock <= 0:
                        product.stock = 0
                        product.is_available = False

                    product.save()


        # Order creation succeeded,
        # so invalidate checkout token
        request.session.pop(
            "checkout_token",
            None
        )


        # ==================================
        # ONLINE PAYMENT
        # ==================================

        if payment_method == "online":

            client = razorpay.Client(
                auth=(
                    settings.RAZORPAY_KEY_ID,
                    settings.RAZORPAY_KEY_SECRET
                )
            )

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

                return render(
                    request,
                    "store/payment_failed.html",
                    {
                        "order": order,
                        "error": "We couldn't start the payment. Please try again."
                    }
                )

            request.session[
                "current_order_id"
            ] = order.id

            request.session[
                "razorpay_order_id"
            ] = razorpay_order["id"]

            return render(
                request,
                "store/payment.html",
                {
                    "order": order,
                    "razorpay_order_id":
                        razorpay_order["id"],
                    "razorpay_key_id":
                        settings.RAZORPAY_KEY_ID,
                    "amount":
                        amount_in_paise,
                }
            )


        # ==================================
        # COD SUCCESS
        # ==================================

        elif payment_method == "cod":

            send_order_confirmation(order)

            request.session["cart"] = {}

            return redirect(
                "order_success",
                order_id=order.id
            )


    # --------------------------------
    # NORMAL CHECKOUT PAGE
    # --------------------------------

    context = {
        "cart_items": cart_items,
        "total": total,
        "default_address": default_address,
        "addresses": addresses,
        "checkout_token": checkout_token,
    }

    return render(
        request,
        "store/checkout.html",
        context
    )
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
        product.price = request.POST.get("price")
        product.stock = request.POST.get("stock")
        product.is_available = request.POST.get("is_available") == "on"
        new_image = request.FILES.get("image")

        if new_image:
            product.image = new_image
        product.save()

        return redirect("crm_inventory")

    return render(
        request,
        "store/crm_inventory_edit.html",
        {"product": product}
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

    if request.method == "POST":
        new_status = request.POST.get("status")

        valid_statuses = [
            "pending",
            "confirmed",
            "shipped",
            "delivered",
            "cancelled",
        ]

        if new_status in valid_statuses:

            old_status = order.status

            # If order is newly cancelled, return stock
            if new_status == "cancelled" and old_status != "cancelled":

                for item in order.items.all():
                    product = item.product
                    product.stock += item.quantity
                    product.is_available = True
                    product.save()

            # If cancelled order is changed back to active,
            # reduce stock again
            elif old_status == "cancelled" and new_status != "cancelled":

                can_restore_order = True

                for item in order.items.all():
                    if item.product.stock < item.quantity:
                        can_restore_order = False
                        break

                if can_restore_order:

                    for item in order.items.all():
                        product = item.product
                        product.stock -= item.quantity

                        if product.stock <= 0:
                            product.stock = 0
                            product.is_available = False

                        product.save()

                else:
                    return redirect("crm_orders")

            order.status = new_status

# COD becomes paid only when delivered
            if order.payment_method == "cod":

                if new_status == "delivered":
                    order.payment_status = "paid"

                elif new_status == "cancelled" and order.payment_status != "paid":
                    order.payment_status = "pending"

                order.save()

                # Send email only if the status actually changed
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
        Product.objects.create(
            name=request.POST.get("name"),
            category=request.POST.get("category"),
            price=request.POST.get("price"),
            stock=request.POST.get("stock"),
            description=request.POST.get("description"),
            image=request.FILES.get("image"),
            is_available=request.POST.get("is_available") == "on",
        )

        return redirect("crm_inventory")

    return render(
        request,
        "store/crm_inventory_add.html"
    )
def product_detail(request, product_id):
    product = get_object_or_404(Product, id=product_id)

    reviews = product.reviews.all().order_by("-created_at")

    average_rating = product.reviews.aggregate(
        average=Avg("rating")
    )["average"] or 0

    user_review = None

    if request.user.is_authenticated:
        user_review = Review.objects.filter(
            product=product,
            user=request.user
        ).first()
    is_saved = False

    if request.user.is_authenticated:
        is_saved = Wishlist.objects.filter(
            user=request.user,
            product=product
        ).exists()
    context = {
        "product": product,
        "reviews": reviews,
        "average_rating": average_rating,
        "user_review": user_review,
        "is_saved": is_saved,
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
def dog_products(request):
    products = Product.objects.filter(
        category="dog_food",
        is_available=True
    )

    return render(
        request,
        "store/category_products.html",
        {
            "products": products,
            "page_title": "Dog Food",
        }
    )


def cat_products(request):
    products = Product.objects.filter(
        category="cat_food",
        is_available=True
    )

    return render(
        request,
        "store/category_products.html",
        {
            "products": products,
            "page_title": "Cat Food",
        }
    )


def medicine_products(request):
    products = Product.objects.filter(
        category="medicine",
        is_available=True
    )

    return render(
        request,
        "store/category_products.html",
        {
            "products": products,
            "page_title": "Pet Medicines",
        }
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
    address = get_object_or_404(
        Address,
        id=address_id,
        user=request.user
    )

    if request.method == "POST":
        # Re-check stock right before creating the order
        for item in cart_items:
            product = Product.objects.get(id=item["product"].id)

            if item["quantity"] > product.stock:
                return render(
                    request,
                    "store/checkout.html",
                    {
                        "cart_items": cart_items,
                        "total": total,
                        "default_address": default_address,
                        "addresses": addresses,
                        "error": (
                            f"Sorry, only {product.stock} unit(s) of "
                            f"{product.name} are available."
                        ),
                    }
                )
        address.full_name = request.POST.get("full_name")
        address.phone = request.POST.get("phone")
        address.address_line1 = request.POST.get("address_line1")
        address.address_line2 = request.POST.get("address_line2")
        address.city = request.POST.get("city")
        address.state = request.POST.get("state")
        address.pincode = request.POST.get("pincode")

        is_default = request.POST.get("is_default") == "on"

        if is_default:
            Address.objects.filter(
                user=request.user
            ).exclude(id=address.id).update(is_default=False)

        address.is_default = is_default
        address.save()

        return redirect("my_addresses")

    return render(
        request,
        "store/edit_address.html",
        {"address": address}
    )


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

    razorpay_payment_id = request.GET.get(
        "razorpay_payment_id"
    )

    razorpay_order_id = request.GET.get(
        "razorpay_order_id"
    )

    razorpay_signature = request.GET.get(
        "razorpay_signature"
    )


    order_id = request.session.get(
        "current_order_id"
    )

    saved_razorpay_order_id = (
        request.session.get(
            "razorpay_order_id"
        )
    )


    if not order_id:
        return redirect("home")


    order = get_object_or_404(
        Order,
        id=order_id
    )


    # Make sure Razorpay returned the same
    # order that we created
    if (
        saved_razorpay_order_id
        != razorpay_order_id
    ):

        order.payment_status = "failed"
        order.save()

        return render(
            request,
            "store/payment_failed.html",
            {"order": order}
        )


    client = razorpay.Client(
        auth=(
            settings.RAZORPAY_KEY_ID,
            settings.RAZORPAY_KEY_SECRET
        )
    )


    try:

        client.utility.verify_payment_signature({

            "razorpay_order_id":
                razorpay_order_id,

            "razorpay_payment_id":
                razorpay_payment_id,

            "razorpay_signature":
                razorpay_signature,
        })


        # --------------------------------
        # ONLY PROCESS PAYMENT ONCE
        # --------------------------------

        if order.payment_status != "paid":

            with transaction.atomic():

                for item in order.items.select_related("product").all():

                    product = Product.objects.select_for_update().get(
                        id=item.product.id
                    )

                    if item.quantity > product.stock:
                        raise ValueError(
                            f"Not enough stock for {product.name}"
                        )

                    product.stock -= item.quantity

                    if product.stock <= 0:
                        product.stock = 0
                        product.is_available = False

                    product.save()

                order.payment_status = "paid"
                order.status = "confirmed"
                order.save()
            send_order_confirmation(order)

        # Clear cart only after payment success
        request.session["cart"] = {}


        request.session.pop(
            "current_order_id",
            None
        )

        request.session.pop(
            "razorpay_order_id",
            None
        )


        return redirect(
            "order_success",
            order_id=order.id
        )


    except razorpay.errors.SignatureVerificationError:

        order.payment_status = "failed"
        order.save()


        return render(
            request,
            "store/payment_failed.html",
            {
                "order": order
            }
        )
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