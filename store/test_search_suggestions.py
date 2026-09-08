from django.test import TestCase
from django.urls import reverse
from .models import Product, ProductVariant


class SearchSuggestionTests(TestCase):
    def test_short_queries_are_empty(self):
        response = self.client.get(reverse('search_suggestions'), {'q': 'r'})
        self.assertEqual(response.json(), {'brands': [], 'products': []})

    def test_available_products_only_and_variant_price(self):
        common = dict(brand='Royal Canin', category='dog_food', product_type='food', price=100)
        product = Product.objects.create(name='Royal Canin Adult', stock=0, **common)
        ProductVariant.objects.create(product=product, size='1 KG', price=250, stock=3, is_available=True)
        Product.objects.create(name='Royal Canin archived', stock=5, is_archived=True, **common)
        Product.objects.create(name='Royal Canin unavailable', stock=5, is_available=False, **common)
        Product.objects.create(name='Royal Canin empty', stock=0, **common)
        data = self.client.get(reverse('search_suggestions'), {'q': 'roy'}).json()
        self.assertEqual(len(data['products']), 1)
        self.assertEqual(data['products'][0]['price'], '250.00')
        self.assertEqual(data['brands'][0]['name'], 'Royal Canin')

    def test_results_are_bounded(self):
        for i in range(8):
            Product.objects.create(name=f'Royal food {i}', brand='Royal', category='dog_food', product_type='food', price=100, stock=5)
        data = self.client.get(reverse('search_suggestions'), {'q': 'roy'}).json()
        self.assertEqual(len(data['products']), 5)
