from django.db import models
from django.contrib.auth.models import User


class Product(models.Model):

    PET_TYPE_CHOICES = [
        ("dog", "Dog"),
        ("cat", "Cat"),
        ("both", "Dog & Cat"),
    ]

    LIFE_STAGE_CHOICES = [
        ("puppy_kitten", "Puppy / Kitten"),
        ("adult", "Adult"),
        ("senior", "Senior"),
        ("all", "All Life Stages"),
    ]

    CATEGORY_CHOICES = [

        # DOG
        ("dog_food", "Dog Food"),
        ("dog_treat", "Dog Treats"),
        ("dog_toy", "Dog Toys"),
        ("dog_grooming", "Dog Grooming"),
        ("dog_accessory", "Dog Accessories"),
        ("dog_health", "Dog Health"),

        # CAT
        ("cat_food", "Cat Food"),
        ("cat_treat", "Cat Treats"),
        ("cat_toy", "Cat Toys"),
        ("cat_litter", "Cat Litter"),
        ("cat_grooming", "Cat Grooming"),
        ("cat_accessory", "Cat Accessories"),
        ("cat_health", "Cat Health"),

        # PHARMACY
        ("medicine", "Medicine"),
        ("supplement", "Supplements"),
        ("skin_coat", "Skin & Coat"),
        ("dental", "Dental Care"),
        ("joint_care", "Joint Care"),
        ("digestive", "Digestive Care"),

        # OLD VALUES - KEEP FOR EXISTING PRODUCTS
        ("treat", "Treat"),
        ("accessory", "Accessory"),
    ]

    name = models.CharField(
        max_length=200
    )

    brand = models.CharField(
        max_length=100,
        blank=True
    )

    pet_type = models.CharField(
        max_length=10,
        choices=PET_TYPE_CHOICES,
        blank=True
    )

    category = models.CharField(
        max_length=50,
        choices=CATEGORY_CHOICES
    )

    life_stage = models.CharField(
        max_length=20,
        choices=LIFE_STAGE_CHOICES,
        blank=True
    )

    flavour = models.CharField(
        max_length=100,
        blank=True
    )

    key_benefits = models.TextField(
        blank=True
    )

    price = models.DecimalField(
        max_digits=10,
        decimal_places=2
    )

    original_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        blank=True,
        null=True
    )

    stock = models.PositiveIntegerField(
        default=0
    )

    description = models.TextField(
        blank=True
    )

    image = models.ImageField(
        upload_to="products/",
        blank=True,
        null=True
    )

    is_available = models.BooleanField(
        default=True
    )

    is_featured = models.BooleanField(
        default=False
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    def __str__(self):
        return self.name

class ProductVariant(models.Model):

    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="variants"
    )

    size = models.CharField(
        max_length=50
    )
    image = models.ImageField(
    upload_to="product_variants/",
    blank=True,
    null=True
    )
    price = models.DecimalField(
        max_digits=10,
        decimal_places=2
    )

    original_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        blank=True,
        null=True
    )

    stock = models.PositiveIntegerField(
        default=0
    )

    sku = models.CharField(
        max_length=100,
        blank=True,
        unique=True,
        null=True
    )

    is_available = models.BooleanField(
        default=True
    )

    def __str__(self):
        return f"{self.product.name} - {self.size}"
class FeedingGuide(models.Model):

    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="feeding_guides"
    )

    min_weight = models.DecimalField(
        max_digits=5,
        decimal_places=2
    )

    max_weight = models.DecimalField(
        max_digits=5,
        decimal_places=2
    )

    daily_grams = models.PositiveIntegerField()

    def __str__(self):
        return (
            f"{self.product.name}: "
            f"{self.min_weight}-{self.max_weight} KG "
            f"→ {self.daily_grams} g/day"
        )
class Order(models.Model):
    user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="orders"
    )
    PAYMENT_STATUS_CHOICES = [
        ("pending", "Pending"),
        ("paid", "Paid"),
        ("failed", "Failed"),
        ("refunded", "Refunded"),
    ]
    payment_status = models.CharField(
        max_length=20,
        choices=PAYMENT_STATUS_CHOICES,
        default="pending"
    )

    PAYMENT_CHOICES = [
        ("cod", "Cash on Delivery"),
        ("online", "Online Payment"),
    ]

    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("confirmed", "Confirmed"),
        ("shipped", "Shipped"),
        ("delivered", "Delivered"),
        ("cancelled", "Cancelled"),
    ]

    customer_name = models.CharField(max_length=150)
    email = models.EmailField()
    phone = models.CharField(max_length=20)
    address = models.TextField()

    payment_method = models.CharField(
        max_length=20,
        choices=PAYMENT_CHOICES,
        default="cod"
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="pending"
    )

    total_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0
    )

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Order #{self.id} - {self.customer_name}"


class OrderItem(models.Model):
    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name="items"
    )

    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE
    )

    variant = models.ForeignKey(
        ProductVariant,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="order_items"
    )

    # Snapshot the package size so old orders still show
    # the purchased size even if that variant is deleted later.
    variant_size = models.CharField(
        max_length=50,
        blank=True
    )

    quantity = models.PositiveIntegerField()

    price = models.DecimalField(
        max_digits=10,
        decimal_places=2
    )

    def __str__(self):
        if self.variant_size:
            return (
                f"{self.product.name} "
                f"({self.variant_size}) x {self.quantity}"
            )

        return f"{self.product.name} x {self.quantity}"


class Pet(models.Model):
    PET_TYPE_CHOICES = [
        ("dog", "Dog"),
        ("cat", "Cat"),
    ]

    owner = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="pets"
    )

    name = models.CharField(max_length=100)

    pet_type = models.CharField(
        max_length=10,
        choices=PET_TYPE_CHOICES
    )

    breed = models.CharField(max_length=100, blank=True)

    age = models.PositiveIntegerField(
        blank=True,
        null=True
    )

    weight = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        blank=True,
        null=True
    )

    notes = models.TextField(blank=True)

    def __str__(self):
        return f"{self.name} - {self.owner.username}"

class Review(models.Model):
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="reviews"
    )

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE
    )

    rating = models.PositiveIntegerField()

    comment = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("product", "user")

    def __str__(self):
        return f"{self.product.name} - {self.rating} stars"

class Wishlist(models.Model):
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="wishlist_items"
    )

    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="wishlisted_by"
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("user", "product")

    def __str__(self):
        return f"{self.user.username} - {self.product.name}"

class Address(models.Model):
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="addresses"
    )

    full_name = models.CharField(max_length=100)
    phone = models.CharField(max_length=15)

    address_line1 = models.CharField(max_length=255)
    address_line2 = models.CharField(
        max_length=255,
        blank=True
    )

    city = models.CharField(max_length=100)
    state = models.CharField(max_length=100)
    pincode = models.CharField(max_length=10)

    is_default = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.full_name} - {self.city}"