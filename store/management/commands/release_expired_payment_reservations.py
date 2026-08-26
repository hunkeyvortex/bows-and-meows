from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from store.models import Order, Product, ProductVariant
from store.services.order_notifications import notify_payment_failed


def expire_online_reservation(order_id):
    """Atomically fail an abandoned payment and return its reserved stock."""
    with transaction.atomic():
        order = Order.objects.select_for_update().get(id=order_id)
        if (
            order.payment_method != "online"
            or order.payment_status != "pending"
            or not order.inventory_reserved
        ):
            return None

        affected_products = set()
        items = order.items.select_related("product", "variant").order_by(
            "product_id", "variant_id", "id"
        )
        for item in items:
            if item.variant_id:
                variant = ProductVariant.objects.select_for_update().filter(id=item.variant_id).first()
                if variant:
                    variant.stock += item.quantity
                    variant.is_available = True
                    variant.save(update_fields=["stock", "is_available"])
                    affected_products.add(item.product_id)
            else:
                product = Product.objects.select_for_update().filter(id=item.product_id).first()
                if product:
                    product.stock += item.quantity
                    product.is_available = True
                    product.save(update_fields=["stock", "is_available"])

        for product_id in sorted(affected_products):
            product = Product.objects.select_for_update().get(id=product_id)
            variants = list(product.variants.all())
            product.stock = sum(variant.stock for variant in variants)
            product.is_available = any(
                variant.stock > 0 and variant.is_available for variant in variants
            )
            product.save(update_fields=["stock", "is_available"])

        order.inventory_reserved = False
        order.payment_status = "failed"
        order.save(update_fields=["inventory_reserved", "payment_status"])
        return order


class Command(BaseCommand):
    help = "Release inventory held by abandoned pending online-payment orders."

    def handle(self, *args, **options):
        cutoff = timezone.now() - timedelta(minutes=settings.PAYMENT_RESERVATION_MINUTES)
        order_ids = list(
            Order.objects.filter(
                payment_method="online",
                payment_status="pending",
                inventory_reserved=True,
                created_at__lt=cutoff,
            ).values_list("id", flat=True)
        )

        released = 0
        for order_id in order_ids:
            order = expire_online_reservation(order_id)
            if order:
                released += 1
                notify_payment_failed(order)

        self.stdout.write(self.style.SUCCESS(f"Released {released} expired reservation(s)."))
