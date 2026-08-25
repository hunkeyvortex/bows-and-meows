from pathlib import Path

from django import forms
from django.forms import inlineformset_factory
from django.core.exceptions import ValidationError

from .models import BundleItem, DeliveryZone, OfferCampaign, Prescription, Product, ProductBundle, ProductVariant


class PrescriptionUploadForm(forms.ModelForm):
    class Meta:
        model = Prescription
        fields = ("pet", "file")
        widgets = {"file": forms.ClearableFileInput(attrs={"accept": ".jpg,.jpeg,.png,.pdf"})}

    def clean_file(self):
        uploaded = self.cleaned_data["file"]
        extension = Path(uploaded.name).suffix.lower()
        if extension not in {".jpg", ".jpeg", ".png", ".pdf"}:
            raise ValidationError("Upload a JPG, JPEG, PNG or PDF file.")
        if uploaded.size > 5 * 1024 * 1024:
            raise ValidationError("The prescription must be 5 MB or smaller.")
        allowed_types = {"image/jpeg", "image/png", "application/pdf"}
        content_type = getattr(uploaded, "content_type", "")
        if content_type and content_type not in allowed_types:
            raise ValidationError("This file type is not allowed.")
        return uploaded


class DeliveryZoneForm(forms.ModelForm):
    class Meta:
        model = DeliveryZone
        fields = "__all__"


class OfferCampaignForm(forms.ModelForm):
    class Meta:
        model = OfferCampaign
        fields = "__all__"
        widgets = {"categories": forms.Textarea(attrs={"rows": 2, "placeholder": '["dog", "cat"]'})}


class ProductBundleForm(forms.ModelForm):
    class Meta:
        model = ProductBundle
        fields = "__all__"


class BundleItemForm(forms.ModelForm):
    """Keep bundle selects small; choices are populated by CRM search endpoints."""

    class Meta:
        model = BundleItem
        fields = ("product", "variant", "quantity")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        product_id = self.data.get(f"{self.prefix}-product") if self.is_bound else self.instance.product_id
        variant_id = self.data.get(f"{self.prefix}-variant") if self.is_bound else self.instance.variant_id
        self.fields["product"].queryset = Product.objects.filter(pk=product_id) if product_id else Product.objects.none()
        self.fields["variant"].queryset = ProductVariant.objects.filter(pk=variant_id) if variant_id else ProductVariant.objects.none()
        self.fields["product"].widget.attrs.update({"class": "bm-remote-product", "data-search-url": "/crm/bundles/products/search/"})
        self.fields["variant"].widget.attrs.update({"class": "bm-remote-variant", "data-search-url": "/crm/bundles/variants/search/"})


BundleItemFormSet = inlineformset_factory(
    ProductBundle, BundleItem, form=BundleItemForm, extra=2, can_delete=True
)
