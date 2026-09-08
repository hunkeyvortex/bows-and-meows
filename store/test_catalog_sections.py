from django.test import TestCase
from .models import Product
from .catalog_sections import filter_section, paused_catalog_query


class CatalogSectionsTests(TestCase):
    def make(self, name, **fields):
        return Product.objects.create(name=name, price=100, stock=5, **fields)

    def test_archive_selection_preserves_food(self):
        food = self.make("Skin and Coat Dry Dog Food", product_type="food", category="dog_food")
        clothing = self.make("Festive Bandana for Dogs", product_type="food", category="dog_food")
        medicine = self.make("Medicine", product_type="medicine", category="dog_food")
        prescription = self.make("Prescription item", requires_prescription=True)
        selected = Product.objects.filter(paused_catalog_query())
        self.assertNotIn(food, selected)
        for item in (clothing, medicine, prescription):
            self.assertIn(item, selected)
        self.assertIn(food, Product.objects.customer_visible())

    def test_food_sections_do_not_overlap(self):
        dry = self.make("Chicken Dry Food", product_type="food")
        wet = self.make("Chicken in Gravy", product_type="food")
        self.assertEqual(list(filter_section(Product.objects.all(), "dry")), [dry])
        self.assertEqual(list(filter_section(Product.objects.all(), "wet")), [wet])
