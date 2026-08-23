import re
from decimal import Decimal

from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone


class Product(models.Model):

    PET_TYPE_CHOICES = [
        ("dog", "Dog"),
        ("cat", "Cat"),
        ("both", "Dog & Cat"),
        ("bird", "Bird"),
        ("exotic", "Exotic Pet"),
        ("small_pet", "Small Pet"),
        ("farm", "Farm Animal"),
        ("fish_reptile", "Fish & Reptile"),
    ]

    PRODUCT_TYPE_CHOICES = [
        ("food", "Food"),
        ("medicine", "Medicine"),
        ("supplement", "Supplement"),
        ("treat", "Treat"),
        ("supply", "Supply & Accessory"),
        ("grooming", "Grooming & Hygiene"),
        ("vaccine", "Vaccination"),
    ]

    CARE_AREA_CHOICES = [
        ("", "General / Not Applicable"),
        ("allergy", "Allergy Relief"),
        ("antibiotic", "Antibiotic"),
        ("anxiety", "Anxiety Care"),
        ("cancer", "Cancer Care"),
        ("cardiac", "Cardiac Care"),
        ("deworming", "Deworming"),
        ("diabetes", "Diabetes Care"),
        ("eye_ear", "Eye & Ear Care"),
        ("flea_tick", "Flea & Tick Care"),
        ("digestive", "Digestive Care"),
        ("joint", "Hip & Joint Care"),
        ("immunity", "Immunity Support"),
        ("liver", "Liver Care"),
        ("prenatal", "Pre & Post Natal Care"),
        ("respiratory", "Respiratory Care"),
        ("skin_coat", "Skin & Coat Care"),
        ("renal", "Renal & Urinary Care"),
        ("wound_pain", "Wound & Pain Relief"),
        ("dental", "Dental & Oral Care"),
        ("nutrition", "Everyday Nutrition"),
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
        ("parasite_control", "Flea, Tick & Deworming"),
        ("respiratory_care", "Respiratory Care"),
        ("kidney_care", "Kidney & Urinary Care"),
        ("heart_care", "Heart Care"),

        # GROOMING & HYGIENE
        ("grooming_shampoo", "Shampoo & Coat Care"),
        ("hygiene", "Hygiene & Cleaning"),
        ("training_pads", "Training Pads"),

        # BIRDS & EXOTIC PETS
        ("bird_food", "Bird Food"),
        ("bird_supplement", "Bird Supplements"),
        ("bird_health", "Bird Health"),
        ("exotic_health", "Exotic Pet Health"),

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
        max_length=15,
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

    product_type = models.CharField(
        max_length=20,
        choices=PRODUCT_TYPE_CHOICES,
        blank=True,
        db_index=True,
    )

    care_area = models.CharField(
        max_length=30,
        choices=CARE_AREA_CHOICES,
        blank=True,
        db_index=True,
    )

    target_species = models.CharField(
        max_length=120,
        blank=True,
        help_text="Examples: Dogs, cats, budgies, exotic birds.",
    )

    active_ingredients = models.TextField(
        blank=True,
        help_text="Active ingredients exactly as printed on the package.",
    )

    usage_warning = models.TextField(
        blank=True,
        help_text="Safety, dosage or veterinary-use warning shown to customers.",
    )

    requires_prescription = models.BooleanField(
        default=False,
        help_text="Blocks ordinary cart purchase and displays a prescription warning.",
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

    manufacturer_name = models.CharField(max_length=180, blank=True)
    manufacturer_address = models.TextField(blank=True)
    country_of_origin = models.CharField(max_length=100, blank=True)
    marketed_by = models.CharField(max_length=180, blank=True)
    ingredients = models.TextField(blank=True)
    directions = models.TextField(blank=True)
    specifications = models.TextField(
        blank=True,
        help_text="One specification per line, for example: Breed size: All breeds",
    )

    image = models.ImageField(
        upload_to="products/",
        blank=True,
        null=True
    )

    external_image_url = models.URLField(max_length=1000, blank=True)
    source_url = models.URLField(max_length=1000, blank=True)
    supplier_product_id = models.CharField(max_length=80, blank=True, db_index=True)

    is_available = models.BooleanField(
        default=True
    )

    is_archived = models.BooleanField(
        default=False,
        db_index=True,
        help_text="Hides the product from customers without deleting its history.",
    )

    is_featured = models.BooleanField(
        default=False
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    def __str__(self):
        return self.name

    @property
    def available_variants(self):
        variants = [
            variant for variant in self.variants.all()
            if variant.is_available and variant.stock > 0
        ]
        unique_by_size = {}
        for variant in sorted(variants, key=lambda item: (item.price, item.id)):
            normalized_size = re.sub(r"\s+", "", variant.size).casefold()
            unique_by_size.setdefault(normalized_size, variant)
        return list(unique_by_size.values())

    @property
    def card_variants(self):
        return self.available_variants

    @property
    def has_available_variants(self):
        return bool(self.available_variants)

    @property
    def display_price(self):
        variants = self.available_variants
        return variants[0].price if variants else self.price

    @property
    def display_original_price(self):
        variants = self.available_variants
        if variants:
            return variants[0].original_price
        return self.original_price

    @property
    def display_discount_percent(self):
        price = self.display_price
        original_price = self.display_original_price
        if not original_price or original_price <= price:
            return 0
        return round(((original_price - price) / original_price) * 100)

    @property
    def display_image_url(self):
        if self.image:
            try:
                return self.image.url
            except (ValueError, AttributeError):
                pass
        return self.external_image_url

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
    external_image_url = models.URLField(max_length=1000, blank=True)
    supplier_variant_id = models.CharField(max_length=80, blank=True, db_index=True)
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

    @property
    def display_image_url(self):
        if self.image:
            try:
                return self.image.url
            except (ValueError, AttributeError):
                pass
        return self.external_image_url or self.product.display_image_url

class ProductImage(models.Model):

    IMAGE_TYPE_CHOICES = [
        ("gallery", "Gallery"),
        ("ingredients", "Ingredients"),
        ("nutrition", "Nutrition"),
        ("feeding", "Feeding Guide"),
        ("lifestyle", "Lifestyle"),
        ("other", "Other"),
    ]

    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="gallery_images"
    )

    image = models.ImageField(
        upload_to="products/gallery/",
        blank=True,
        null=True,
    )

    external_image_url = models.URLField(max_length=1000, blank=True)

    image_type = models.CharField(
        max_length=20,
        choices=IMAGE_TYPE_CHOICES,
        default="gallery"
    )

    sort_order = models.PositiveIntegerField(
        default=0
    )

    def __str__(self):
        return f"{self.product.name} - {self.image_type}"

    @property
    def display_image_url(self):
        if self.image:
            try:
                return self.image.url
            except (ValueError, AttributeError):
                pass
        return self.external_image_url
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

    inventory_reserved = models.BooleanField(
        default=False,
        help_text="Whether this order's quantities are currently deducted from stock.",
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

    subtotal_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    discount_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    coupon_code = models.CharField(max_length=40, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Order #{self.id} - {self.customer_name}"


class Coupon(models.Model):
    code = models.CharField(max_length=40, unique=True)
    discount_percent = models.PositiveSmallIntegerField(help_text="Percentage from 1 to 100")
    minimum_order = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    maximum_discount = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    is_active = models.BooleanField(default=True)
    starts_at = models.DateTimeField(blank=True, null=True)
    ends_at = models.DateTimeField(blank=True, null=True)
    usage_limit = models.PositiveIntegerField(blank=True, null=True)
    times_used = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ("code",)

    def __str__(self):
        return f"{self.code} ({self.discount_percent}% off)"

    def validation_error(self, subtotal):
        now = timezone.now()
        if not self.is_active:
            return "This coupon is not active."
        if self.starts_at and now < self.starts_at:
            return "This coupon is not active yet."
        if self.ends_at and now > self.ends_at:
            return "This coupon has expired."
        if self.usage_limit is not None and self.times_used >= self.usage_limit:
            return "This coupon has reached its usage limit."
        if subtotal < self.minimum_order:
            return f"Spend at least ₹{self.minimum_order:.2f} to use this coupon."
        return ""

    def discount_for(self, subtotal):
        discount = (subtotal * self.discount_percent / 100).quantize(Decimal("0.01"))
        # Treat an empty or zero cap as unlimited. CRM users commonly enter 0
        # to mean "no maximum", and capping at zero would erase the discount.
        if self.maximum_discount is not None and self.maximum_discount > 0:
            discount = min(discount, self.maximum_discount)
        return min(discount, subtotal)


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

    image = models.ImageField(
        upload_to="pets/",
        blank=True,
        null=True,
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
