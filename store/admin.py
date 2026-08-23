from django.contrib import admin
from .models import Product, Order, OrderItem, Pet, Coupon, ProductImage, ProductVariant


admin.site.register(Product)
admin.site.register(Order)
admin.site.register(OrderItem)
admin.site.register(Pet)
admin.site.register(Coupon)
admin.site.register(ProductImage)
admin.site.register(ProductVariant)
