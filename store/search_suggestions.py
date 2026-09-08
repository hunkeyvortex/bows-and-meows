from urllib.parse import urlencode
from django.http import JsonResponse
from django.db.models import Q
from django.urls import reverse
from django.views.decorators.http import require_GET
from .models import Product


@require_GET
def suggestions(request):
    query = request.GET.get('q', '').strip()[:80]
    if len(query) < 2:
        return JsonResponse({'brands': [], 'products': []})
    visible = Product.objects.customer_visible()
    brands = visible.filter(brand__istartswith=query).order_by('brand').values_list('brand', flat=True).distinct()[:3]
    products = visible.filter(Q(name__icontains=query) | Q(brand__icontains=query)).order_by('name', 'id').prefetch_related('variants')[:5]
    return JsonResponse({
        'brands': [{'name': brand, 'url': reverse('search_products') + '?' + urlencode({'q': brand})} for brand in brands],
        'products': [{'name': p.name, 'url': reverse('product_detail', args=[p.id]),
                      'image': p.display_image_url, 'price': str(p.display_price)} for p in products],
    })
