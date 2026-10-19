from django import forms
from .models import Product, ProductVariant, ProductImage, Promotion


class BootstrapFormMixin:
    """Applies a default Bootstrap class to any field that wasn't given one explicitly."""
    def _apply_bootstrap_classes(self):
        for field in self.fields.values():
            widget = field.widget
            if isinstance(widget, forms.CheckboxInput):
                widget.attrs.setdefault('class', 'form-check-input')
            elif isinstance(widget, (forms.Select, forms.SelectMultiple)):
                widget.attrs.setdefault('class', 'form-select form-select-sm')
            elif 'class' not in widget.attrs:
                widget.attrs.setdefault('class', 'form-control form-control-sm')


class ProductForm(BootstrapFormMixin, forms.ModelForm):
    """Core product fields only. Variants / images / promotions / tags are handled
    separately via their own modal forms once the product exists."""

    class Meta:
        model = Product
        fields = [
            # General
            'name', 'qoute', 'product_type', 'sku','slug', 'category', 'brand',
            'status', 'stock_status',
            'description', 'brief_description', 'admin_comment',
            'available_start_date', 'available_end_date',
            'allow_customer_reviews', 'customer_can_see_stock', 'mark_as_new',
            'available_for_preorder', 'disable_buy_button', 'disable_wishlist_button',
            'show_on_home_page', 'display_order', 'visible_individually', 'video',

            # Pricing
            'price', 'old_price', 'original_price', 'other_product_cost',
            'compare_at', 'compare_at_price', 'discount_percentage', 'bulk_discount_rules',
            'tax_exempt', 'tax_category',

            # Shipping
            'weight', 'length', 'width', 'height', 'shipping_class', 'free_shipping',
            'handling_time', 'shipping_enabled', 'ship_separately',
            'shipping_charges', 'additional_shipping_charges',

            # SEO
            'meta_title', 'meta_description', 'focus_keywords',
        ]
        widgets = {
            'slug': forms.TextInput(
                attrs={
                    'class': 'form-control',
                    'readonly': 'readonly',
                    'id': 'id_slug'
                }
            ),

            'sku': forms.TextInput(
                attrs={
                    'class': 'form-control',
                    'id': 'id_sku',
                    'autocomplete': 'off'
                }
            ),
            'category': forms.SelectMultiple(attrs={'id': 'id_category'}),
            'description': forms.Textarea(attrs={'rows': 5, 'id': 'id_description'}),
            'brief_description': forms.Textarea(attrs={'rows': 3}),
            'admin_comment': forms.Textarea(attrs={'rows': 3}),
            'bulk_discount_rules': forms.Textarea(attrs={'rows': 2}),
            'meta_description': forms.Textarea(attrs={'rows': 2}),
            'available_start_date': forms.DateInput(attrs={'type': 'date'}),
            'available_end_date': forms.DateInput(attrs={'type': 'date'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._apply_bootstrap_classes()
        # These have model-level defaults, so make them feel optional in the UI
        # even though they're technically required fields on the model.
        for name in ('weight', 'length', 'width', 'height', 'handling_time',
                     'shipping_charges', 'additional_shipping_charges', 'compare_at'):
            self.fields[name].required = False

    def clean(self):
        cleaned = super().clean()
        # Fall back to the model defaults for the "optional in the UI" fields above.
        defaults = {
            'weight': 0, 'length': 0, 'width': 0, 'height': 0,
            'handling_time': 1, 'shipping_charges': 0, 'additional_shipping_charges': 0,
            'compare_at': 0,
        }
        for field, default in defaults.items():
            if cleaned.get(field) in (None, ''):
                cleaned[field] = default
        return cleaned


class ColorInput(forms.TextInput):
    input_type = "color"

import re
from django.core.validators import RegexValidator
from django.db import transaction

class ProductVariantForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = ProductVariant
        fields = ['name', 'sku', 'price', 'stock_quantity', 'images']   # 'image' removed
        widgets = {
            'name': forms.TextInput(attrs={'placeholder': 'e.g. Color: Red, Size: XL'}),
            'price': forms.NumberInput(attrs={'step': '0.01'}),
            'images': forms.CheckboxSelectMultiple,
        }

    def __init__(self, *args, product=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._apply_bootstrap_classes()
        self.fields['images'].required = False
        self._color_matches = []

        if product is not None:
            self.fields['images'].queryset = product.images.all()
            if self.instance.pk:
                self._add_color_fields(product)

        # Legacy rows: only the old single FK is set, so pre-select it
        if self.instance.pk and not self.is_bound:
            if not self.instance.images.exists() and self.instance.image_id:
                self.initial['images'] = [self.instance.image_id]

    def selected_image_ids(self):
        # After a failed POST, keep whatever the user had ticked
        if self.is_bound:
            return {int(v) for v in self.data.getlist('images') if v.isdigit()}
        ids = set()
        if self.instance.pk:
            ids = set(self.instance.images.values_list('pk', flat=True))
            if self.instance.image_id:          # legacy rows / primary image
                ids.add(self.instance.image_id)
        return ids
    def _add_color_fields(self, product):
        # "Red / Small" or "Color: Red, Size: XL" -> ["Red", "Small"]
        parts = [p.split(":")[-1].strip().lower()
                 for p in re.split(r"\s*[/,]\s*", self.instance.name) if p.strip()]

        for opt in product.variant_options.all():
            if not opt.is_color:
                continue
            labels = opt.get_options_list()
            for i, label in enumerate(labels):
                if label.lower() in parts:
                    name = f"color_{opt.pk}"
                    self.fields[name] = forms.CharField(
                        label=f"{opt.option_name} code ({label})",
                        required=False,
                        initial=opt.get_color_at(i) or "#000000",
                        widget=ColorInput(attrs={"class": "form-control form-control-color"}),
                        validators=[RegexValidator(r"^#[0-9a-fA-F]{6}$", "Enter a valid hex color.")],
                        help_text=f'Changes the color for every "{label}" variant of this product.',
                    )
                    self._color_matches.append((opt, i, label, name))
                    break  # one match per option group

    @property
    def color_fields(self):
        return [self[name] for *_, name in self._color_matches]

    def save_color_codes(self, user=None):
        with transaction.atomic():
            for opt, idx, _label, name in self._color_matches:
                code = self.cleaned_data.get(name)
                if not code:
                    continue
                opt.set_color_at(idx, code)
                if user:
                    opt.modified_by = user
                opt.save()


class ProductImageForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = ProductImage
        fields = ['image', 'is_primary', 'alt_text']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._apply_bootstrap_classes()
        self.fields['image'].required = True


class PromotionForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Promotion
        fields = [
            'name', 'description', 'promo_code', 'discount_type', 'discount_value',
            'compare_at_price', 'discounted_price', 'start_date', 'end_date', 'show_on_home',
        ]
        widgets = {
            'description': forms.Textarea(attrs={'rows': 2}),
            'discount_value': forms.NumberInput(attrs={'step': '0.01'}),
            'start_date': forms.DateTimeInput(attrs={'type': 'datetime-local'}, format='%Y-%m-%dT%H:%M'),
            'end_date': forms.DateTimeInput(attrs={'type': 'datetime-local'}, format='%Y-%m-%dT%H:%M'),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._apply_bootstrap_classes()

    def clean(self):
        cleaned = super().clean()
        start = cleaned.get('start_date')
        end = cleaned.get('end_date')
        if start and end and end <= start:
            self.add_error('end_date', 'End date must be after the start date.')
        return cleaned


class TagAddForm(forms.Form):
    tag_name = forms.CharField(
        max_length=100,
        label='Tag name',
        widget=forms.TextInput(attrs={
            'class': 'form-control form-control-sm',
            'placeholder': 'e.g. summer-sale',
        }),
    )
