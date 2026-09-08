from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.test import TestCase
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode


class PasswordResetFlowTests(TestCase):
    def test_reset_changes_password_and_shows_confirmation(self):
        user = get_user_model().objects.create_user(
            username="reset-test", email="reset@example.com", password="Old-test-481!"
        )
        url = reverse("password_reset_confirm", kwargs={
            "uidb64": urlsafe_base64_encode(force_bytes(user.pk)),
            "token": default_token_generator.make_token(user),
        })
        response = self.client.get(url)
        form_url = response.url
        invalid = self.client.post(form_url, {
            "new_password1": "New-test-952!", "new_password2": "different",
        })
        self.assertContains(invalid, "errorlist")
        user.refresh_from_db()
        self.assertTrue(user.check_password("Old-test-481!"))
        response = self.client.post(form_url, {
            "new_password1": "New-test-952!", "new_password2": "New-test-952!",
        }, follow=True)
        self.assertContains(response, "Password changed successfully")
        user.refresh_from_db()
        self.assertTrue(user.check_password("New-test-952!"))
        self.assertFalse(user.check_password("Old-test-481!"))
