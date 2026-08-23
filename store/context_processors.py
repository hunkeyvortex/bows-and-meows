from django.conf import settings


def customer_support(request):
    number = "".join(character for character in settings.WHATSAPP_NUMBER if character.isdigit())
    cart_item_count = 0
    for entry in request.session.get("cart", {}).values():
        try:
            quantity = entry.get("quantity", 1) if isinstance(entry, dict) else entry
            cart_item_count += max(int(quantity), 0)
        except (TypeError, ValueError):
            continue
    return {
        "support_email": settings.SUPPORT_EMAIL,
        "whatsapp_number": number,
        "google_oauth_ready": bool(
            settings.GOOGLE_OAUTH_CLIENT_ID and settings.GOOGLE_OAUTH_CLIENT_SECRET
        ),
        "cart_item_count": cart_item_count,
    }
