from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from .models import Product


class CRMDashboardTests(TestCase):
    def test_archived_products_are_not_low_stock_alerts(self):
        staff = User.objects.create_user(username="crm-test", is_staff=True)
        self.client.force_login(staff)
        Product.objects.create(name="Archived food", category="dog_food", price=100, stock=0, is_archived=True)
        response = self.client.get(reverse("crm_dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["low_stock_count"], 0)
        self.assertNotContains(response, "Archived food")
