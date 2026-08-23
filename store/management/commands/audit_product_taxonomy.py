from django.core.management.base import BaseCommand
from store.models import Product


STRUCTURED_CATEGORY_PET_TYPES = {
    "dog_": "dog",
    "cat_": "cat",
    "bird_": "bird",
}


class Command(BaseCommand):
    help = "Safely report category/pet-type normalization candidates without changing data."

    def handle(self, *args, **options):
        changes = []
        for category_prefix, expected_pet_type in STRUCTURED_CATEGORY_PET_TYPES.items():
            queryset = Product.objects.filter(category__startswith=category_prefix).exclude(
                pet_type=expected_pet_type
            )
            for product in queryset.only("id", "name", "category", "pet_type"):
                changes.append((product, expected_pet_type))

        self.stdout.write(f"Products requiring normalization: {len(changes)}")
        for product, expected in changes[:100]:
            self.stdout.write(
                f"{product.id}: {product.pet_type or '<blank>'} -> {expected} | "
                f"{product.category} | {product.name}"
            )
        if len(changes) > 100:
            self.stdout.write(f"...and {len(changes) - 100} more")

        self.stdout.write(
            self.style.WARNING(
                "Report only: no records changed. Review supplier category mappings before correction."
            )
        )
