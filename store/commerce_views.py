from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db.models import Q
from django.http import FileResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from .commerce_forms import BundleItemFormSet, DeliveryZoneForm, OfferCampaignForm, PrescriptionUploadForm, ProductBundleForm
from .models import DeliveryZone, OfferCampaign, Prescription, Product, ProductBundle, ProductVariant
from .services.commerce import active_campaigns, bundle_snapshot


def delivery_status(request):
    pincode = (request.POST.get("pincode") or request.GET.get("pincode") or "").strip()
    if not pincode.isdigit() or len(pincode) != 6:
        return JsonResponse({"available": False, "error": "Enter a valid 6-digit pincode."}, status=400)
    zone = DeliveryZone.objects.filter(pincode=pincode, is_active=True).first()
    request.session["delivery_pincode"] = pincode
    request.session.modified = True
    if not zone:
        return JsonResponse({"available": False, "pincode": pincode, "message": "We currently do not deliver to this pincode."})
    return JsonResponse({
        "available": True, "pincode": pincode, "city": zone.city, "state": zone.state,
        "min_days": zone.min_delivery_days, "max_days": zone.max_delivery_days,
        "cod_available": zone.cod_available,
    })


def quick_view(request, product_id):
    product = get_object_or_404(Product.objects.customer_visible().prefetch_related("variants", "gallery_images"), id=product_id)
    return render(request, "store/includes/quick_view_content.html", {"product": product})


@require_POST
def add_frequently_bought(request, product_id):
    anchor = get_object_or_404(Product.objects.customer_visible(), id=product_id)
    selected_ids = [int(value) for value in request.POST.getlist("selected") if value.isdigit()]
    allowed = {item.id: item for item in Product.objects.customer_visible().filter(id__in=selected_ids).prefetch_related("variants")}
    cart = request.session.get("cart", {}) if isinstance(request.session.get("cart", {}), dict) else {}
    for selected_id in selected_ids:
        item = allowed.get(selected_id)
        if not item:
            continue
        variant_id = request.POST.get(f"variant_{item.id}")
        variant = item.variants.filter(id=variant_id, is_available=True, stock__gt=0).first() if variant_id else None
        if item.variants.exists() and not variant:
            messages.error(request, f"Choose an available size for {item.name}.")
            return redirect("product_detail", product_id=anchor.id)
        key = f"p{item.id}" + (f":v{variant.id}" if variant else "")
        cart[key] = {"product_id": item.id, "variant_id": variant.id if variant else None, "quantity": 1}
    request.session["cart"] = cart
    request.session.modified = True
    messages.success(request, "Selected products were added to your cart.")
    return redirect("cart")


def offers(request):
    campaigns = list(active_campaigns())
    category_filters = Q()
    campaign_product_ids = set()
    for campaign in campaigns:
        campaign_product_ids.update(campaign.products.values_list("id", flat=True))
        for category in campaign.categories or []:
            category_filters |= Q(category=category)
    products = Product.objects.customer_visible().filter(
        Q(id__in=campaign_product_ids) | category_filters | Q(original_price__gt=0) | Q(is_featured=True)
    ).distinct().prefetch_related("variants")
    return render(request, "store/offers.html", {"campaigns": campaigns, "products": products})


def bundle_detail(request, slug):
    bundle = get_object_or_404(ProductBundle.objects.prefetch_related("items__product", "items__variant"), slug=slug)
    snapshot = bundle_snapshot(bundle)
    if not bundle.is_current:
        return render(request, "store/bundle_detail.html", {**snapshot, "unavailable": True}, status=404)
    return render(request, "store/bundle_detail.html", snapshot)


@require_POST
def add_bundle(request, slug):
    bundle = get_object_or_404(ProductBundle.objects.prefetch_related("items__product", "items__variant"), slug=slug)
    snapshot = bundle_snapshot(bundle)
    if not snapshot["available"]:
        messages.error(request, "This bundle is currently unavailable.")
        return redirect("bundle_detail", slug=slug)
    regular = snapshot["regular_price"]
    remaining = snapshot["price"]
    cart = request.session.get("cart", {}) if isinstance(request.session.get("cart", {}), dict) else {}
    for index, item in enumerate(snapshot["items"]):
        source_price = item.variant.price if item.variant else item.product.price
        if index == len(snapshot["items"]) - 1:
            allocated_total = remaining
        else:
            allocated_total = (snapshot["price"] * (source_price * item.quantity) / regular).quantize(Decimal("0.01")) if regular else Decimal("0.00")
            remaining -= allocated_total
        unit_price = (allocated_total / item.quantity).quantize(Decimal("0.01"))
        key = f"b{bundle.id}:p{item.product_id}" + (f":v{item.variant_id}" if item.variant_id else "")
        cart[key] = {"product_id": item.product_id, "variant_id": item.variant_id, "quantity": item.quantity,
                     "bundle_id": bundle.id, "bundle_name": bundle.name, "bundle_unit_price": str(unit_price)}
    request.session["cart"] = cart
    request.session.modified = True
    messages.success(request, f"{bundle.name} was added to your cart.")
    return redirect("cart")


@require_POST
def remove_bundle(request, bundle_id):
    cart = request.session.get("cart", {})
    if isinstance(cart, dict):
        request.session["cart"] = {key: value for key, value in cart.items()
            if not (isinstance(value, dict) and str(value.get("bundle_id")) == str(bundle_id))}
        request.session.modified = True
    messages.success(request, "Bundle removed from your cart.")
    return redirect("cart")


@login_required
def prescription_upload(request, product_id):
    product = get_object_or_404(Product.objects.customer_visible(), id=product_id, requires_prescription=True)
    existing = Prescription.objects.filter(user=request.user, product=product).first()
    form = PrescriptionUploadForm(request.POST or None, request.FILES or None)
    form.fields["pet"].queryset = request.user.pets.all()
    if request.method == "POST" and form.is_valid():
        prescription = form.save(commit=False)
        prescription.user = request.user
        prescription.product = product
        prescription.save()
        messages.success(request, "Prescription uploaded. We will notify you after review.")
        return redirect("product_detail", product_id=product.id)
    return render(request, "store/prescription_upload.html", {"form": form, "product": product, "existing": existing})


@login_required
def prescription_download(request, prescription_id):
    prescription = get_object_or_404(Prescription, id=prescription_id)
    if prescription.user_id != request.user.id and not request.user.is_staff:
        return JsonResponse({"error": "Not authorized."}, status=403)
    response = FileResponse(prescription.file.open("rb"), as_attachment=False)
    response["Content-Disposition"] = f'inline; filename="prescription-{prescription.id}"'
    response["X-Content-Type-Options"] = "nosniff"
    return response


staff_required = user_passes_test(lambda user: user.is_staff)


@staff_required
def crm_delivery_zones(request, zone_id=None):
    instance = get_object_or_404(DeliveryZone, id=zone_id) if zone_id else None
    form = DeliveryZoneForm(request.POST or None, instance=instance)
    if request.method == "POST" and form.is_valid():
        form.save(); messages.success(request, "Delivery zone saved."); return redirect("crm_delivery_zones")
    return render(request, "store/crm_delivery_zones.html", {"form": form, "zones": DeliveryZone.objects.all(), "editing": instance})


@staff_required
def crm_offers(request, campaign_id=None):
    instance = get_object_or_404(OfferCampaign, id=campaign_id) if campaign_id else None
    form = OfferCampaignForm(request.POST or None, request.FILES or None, instance=instance)
    if request.method == "POST" and form.is_valid():
        form.save(); messages.success(request, "Offer campaign saved."); return redirect("crm_offers")
    return render(request, "store/crm_offers.html", {"form": form, "campaigns": OfferCampaign.objects.all(), "editing": instance})


@staff_required
def crm_bundles(request, bundle_id=None):
    instance = get_object_or_404(ProductBundle, id=bundle_id) if bundle_id else None
    form = ProductBundleForm(request.POST or None, request.FILES or None, instance=instance)
    formset = BundleItemFormSet(request.POST or None, instance=instance or ProductBundle())
    if request.method == "POST" and form.is_valid() and formset.is_valid():
        bundle = form.save()
        formset.instance = bundle
        formset.save()
        messages.success(request, "Bundle and component items saved.")
        return redirect("crm_bundles")
    bundles = ProductBundle.objects.prefetch_related("items").all()
    return render(request, "store/crm_bundles.html", {"form": form, "formset": formset, "bundles": bundles, "editing": instance})


@staff_required
def crm_bundle_product_search(request):
    query = (request.GET.get("q") or "").strip()
    products = Product.objects.customer_visible().only("id", "name", "brand", "supplier_product_id")
    if query:
        products = products.filter(
            Q(name__icontains=query)
            | Q(brand__icontains=query)
            | Q(supplier_product_id__icontains=query)
            | Q(variants__sku__icontains=query)
        ).distinct()
    else:
        products = products.order_by("-is_featured", "name")
    results = [{"id": product.id, "text": f"{product.name} · {product.brand or 'No brand'} · #{product.id}"} for product in products[:20]]
    return JsonResponse({"results": results})


@staff_required
def crm_bundle_variant_search(request):
    product_id = request.GET.get("product")
    variants = ProductVariant.objects.filter(product_id=product_id).only("id", "size", "sku", "stock") if product_id else ProductVariant.objects.none()
    results = [{"id": variant.id, "text": f"{variant.size} · {variant.sku or 'No SKU'} · Stock {variant.stock}"} for variant in variants[:50]]
    return JsonResponse({"results": results})


@staff_required
def crm_prescriptions(request):
    prescriptions = Prescription.objects.select_related("user", "product", "pet", "reviewed_by")
    return render(request, "store/crm_prescriptions.html", {"prescriptions": prescriptions})


@staff_required
@require_POST
def crm_prescription_review(request, prescription_id):
    prescription = get_object_or_404(Prescription, id=prescription_id)
    action = request.POST.get("action")
    if action not in {"approved", "rejected"}:
        return JsonResponse({"error": "Invalid action."}, status=400)
    prescription.status = action
    prescription.notes = request.POST.get("notes", "").strip()
    prescription.reviewed_by = request.user
    prescription.reviewed_at = timezone.now()
    prescription.save(update_fields=("status", "notes", "reviewed_by", "reviewed_at"))
    messages.success(request, f"Prescription {action}.")
    return redirect("crm_prescriptions")
