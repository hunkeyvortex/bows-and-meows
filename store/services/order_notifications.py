"""Failure-safe, centralized customer notifications for order events."""

import logging
from urllib.parse import urljoin

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.urls import reverse


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
    }


def send_order_notification(order, event):
    """Send one order event through Django's configured backend.

    Callers own transition/deduplication decisions. Delivery errors are logged
    and intentionally never escape into checkout, payment, inventory, or CRM.
    """
    if not order.email or event not in EVENT_CONFIG:
        return False

    subject_template, template_name = EVENT_CONFIG[event]
    context = _context(order, event)
    subject = subject_template.format(number=context["order_number"])
    html = render_to_string(f"store/emails/{template_name}.html", context)
    text = render_to_string(f"store/emails/{template_name}.txt", context)

    try:
        message = EmailMultiAlternatives(
            subject=subject,
            body=text,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[order.email],
        )
        message.attach_alternative(html, "text/html")
        message.send(fail_silently=False)
        return True
    except Exception:
        logger.exception(
            "Could not send %s notification for order %s to %s",
            event,
            order.pk,
            order.email,
        )
        return False


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
