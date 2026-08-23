from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.contrib.auth import get_user_model


class GoogleAccountAdapter(DefaultSocialAccountAdapter):
    """Safely join a verified Google identity to an existing email account."""

    def pre_social_login(self, request, sociallogin):
        if sociallogin.is_existing:
            return
        data = sociallogin.account.extra_data or {}
        email = (data.get("email") or "").strip()
        verified = data.get("email_verified") is True or data.get("verified_email") is True
        if not email or not verified:
            return
        user = get_user_model().objects.filter(email__iexact=email).first()
        if user:
            sociallogin.connect(request, user)
