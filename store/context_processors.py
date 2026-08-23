from django.conf import settings


def customer_support(request):
    number = "".join(character for character in settings.WHATSAPP_NUMBER if character.isdigit())
    return {
        "support_email": settings.SUPPORT_EMAIL,
        "whatsapp_number": number,
        "google_oauth_ready": bool(
            settings.GOOGLE_OAUTH_CLIENT_ID and settings.GOOGLE_OAUTH_CLIENT_SECRET
        ),
    }
