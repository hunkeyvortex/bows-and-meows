"""Failure-safe, centralized customer notifications for order events."""

import logging
from urllib.parse import urljoin, urlsplit
from ipaddress import ip_address

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.urls import reverse
from django.db import transaction
from django.utils import timezone
from django.templatetags.static import static
from store.models import OrderEmailDelivery


logger = logging.getLogger(__name__)


EVENT_CONFIG = {
    "confirmed": ("Boww & Meow — Order {number} confirmed", "order_confirmed"),
    "payment_confirmed": ("Payment confirmed for Boww & Meow order {number}", "payment_confirmed"),
    "packed": ("Your Boww & Meow order {number} is packed", "order_packed"),
    "shipped": ("Your Boww & Meow order {number} is on its way", "order_shipped"),
    "delivered": ("Your Boww & Meow order {number} has been delivered", "order_delivered"),
    "cancelled": ("Boww & Meow order {number} has been cancelled", "order_cancelled"),
    "payment_failed": ("Payment needs attention for Boww & Meow order {number}", "payment_failed"),
}


def order_number(order):
    return f"BM-{order.pk:04d}"


def _absolute_url(path):
    base = getattr(settings, "STOREFRONT_BASE_URL", "").rstrip("/") + "/"
    return urljoin(base, path.lstrip("/")) if base.strip("/") else path


def _context(order, event):
    items = []
    for item in order.items.select_related("product", "variant").all():
        items.append({
            "name": item.product.name,
            "variant": item.variant_size,
            "quantity": item.quantity,
            "unit_price": item.price,
            "line_total": item.price * item.quantity,
            "image_url": _public_image_url(
                item.variant.display_image_url if item.variant_id else item.product.display_image_url
            ) if event != "owner_new_order" else "",
        })

    track_url = ""
    if order.user_id:
        track_url = _absolute_url(reverse("order_detail", args=[order.pk]))

    retry_url = ""
    if order.user_id and event == "payment_failed":
        retry_url = _absolute_url(reverse("retry_payment", args=[order.pk]))

    return {
        "order": order,
        "items": items,
        "event": event,
        "order_number": order_number(order),
        "track_url": track_url,
        "retry_url": retry_url,
        "store_url": _absolute_url(reverse("home")),
        "support_email": getattr(settings, "SUPPORT_EMAIL", ""),
        "crm_url": _absolute_url(reverse("crm_orders")),
        "logo_url": _logo_url() if event != "owner_new_order" else "",
        "progress_stages": [
            {"label": label, "current": order.status == value}
            for value, label in (("confirmed", "Confirmed"), ("packed", "Packed"),
                                 ("shipped", "Shipped"), ("delivered", "Delivered"))
        ] if order.status in {"confirmed", "packed", "shipped", "delivered"} else [],
    }


def _public_image_url(value):
    """Presentation only: omit unsafe/local URLs; never fetch images while sending."""
    if not value:
        return ""
    try:
        url = _absolute_url(value) if value.startswith("/") and not value.startswith("//") else value
        parsed = urlsplit(url)
        host = (parsed.hostname or "").lower()
        if parsed.scheme != "https" or parsed.username or parsed.password or not host:
            return ""
        if host == "localhost" or host.endswith((".localhost", ".local", ".internal")) or "." not in host:
            return ""
        try:
            if not ip_address(host).is_global:
                return ""
        except ValueError:
            pass
        return url
    except ValueError:
        return ""


def _logo_url():
    try:
        return _public_image_url(static("store/images/boww-meow-coral-logo.png"))
    except (ValueError, OSError):
        return ""


def _deliver(order, event, recipient, subject_template, template_name):
    delivery = None
    try:
        # Unique database constraint arbitrates concurrent callbacks/workers.
        # Claim BEFORE contacting Brevo: an uncertain result must not be replayed.
        delivery, created = OrderEmailDelivery.objects.get_or_create(order=order, event=event)
        if not created:
            return False
        context = _context(order, event)
        message = EmailMultiAlternatives(
            subject=subject_template.format(number=context["order_number"]),
            body=render_to_string(f"store/emails/{template_name}.txt", context),
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[recipient],
        )
        message.attach_alternative(render_to_string(f"store/emails/{template_name}.html", context), "text/html")
        accepted = message.send(fail_silently=False) == 1
        OrderEmailDelivery.objects.filter(pk=delivery.pk).update(
            state="sent" if accepted else "failed", completed_at=timezone.now())
        return accepted
    except Exception:
        # Do not log exception text, email addresses, payloads or credentials.
        logger.error("Order email attempt failed: order_id=%s event=%s", order.pk, event)
        if delivery is not None:
            try:
                OrderEmailDelivery.objects.filter(pk=delivery.pk).update(state="failed", completed_at=timezone.now())
            except Exception:
                logger.error("Order email audit update failed: order_id=%s event=%s", order.pk, event)
        return False


def _schedule(order, event, recipient, subject, template):
    if not recipient:
        return False
    try:
        if not transaction.get_connection().in_atomic_block:
            return _deliver(order, event, recipient, subject, template)
        transaction.on_commit(lambda: _deliver(order, event, recipient, subject, template), robust=True)
        return True
    except Exception:
        logger.error("Order email scheduling failed: order_id=%s event=%s", order.pk, event)
        return False


def send_order_notification(order, event):
    if event not in EVENT_CONFIG:
        return False
    return _schedule(order, event, order.email, *EVENT_CONFIG[event])


def notify_owner_new_order(order):
    return _schedule(order, "owner_new_order", settings.ORDER_NOTIFICATION_EMAIL,
                     "New Boww & Meow order {number}", "owner_new_order")


def notify_order_confirmed(order):
    return send_order_notification(order, "confirmed")


def notify_payment_confirmed(order):
    return send_order_notification(order, "payment_confirmed")


def notify_payment_failed(order):
    return send_order_notification(order, "payment_failed")


def notify_order_status(order, old_status):
    """Notify only a real transition to a customer-facing lifecycle state."""
    if old_status == order.status or order.status not in {"confirmed", "packed", "shipped", "delivered", "cancelled"}:
        return False
    return send_order_notification(order, order.status)
