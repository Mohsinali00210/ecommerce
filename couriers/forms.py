import re
from django import forms

from .adapters import adapter_choices
from .models import (CourierCity, CourierCredential, CourierProvider, ShipmentStatus,
                     ShipperProfile, StatusMapping)


class _Bootstrap:
    def _style(self):
        for f in self.fields.values():
            w = f.widget
            if isinstance(w, forms.CheckboxInput):
                w.attrs.setdefault("class", "form-check-input")
            elif isinstance(w, forms.Select):
                w.attrs.setdefault("class", "form-select form-select-sm")
            else:
                w.attrs.setdefault("class", "form-control form-control-sm")


class BookingForm(_Bootstrap, forms.Form):
    provider = forms.ModelChoiceField(queryset=CourierProvider.objects.filter(is_active=True))
    shipper = forms.ModelChoiceField(queryset=ShipperProfile.objects.all(), label="Pickup / return from")
    weight_grams = forms.IntegerField(min_value=1, label="Weight (grams)")
    pieces = forms.IntegerField(min_value=1, initial=1)
    description = forms.CharField(max_length=250, widget=forms.Textarea(attrs={"rows": 2}),
                                  label="Packet description")
    cod_amount = forms.DecimalField(min_value=0, decimal_places=2, label="COD amount (Rs)",
                                    help_text="0 for prepaid orders")
    consignee_name = forms.CharField(max_length=255, label="Customer name")
    consignee_phone = forms.CharField(max_length=30, label="Customer phone")
    consignee_email = forms.EmailField(required=False, label="Customer email")
    consignee_address = forms.CharField(widget=forms.Textarea(attrs={"rows": 2}), label="Delivery address")
    destination_city = forms.ModelChoiceField(queryset=CourierCity.objects.none(), required=False,
                                              label="Destination city (courier list)")
    destination_city_name = forms.CharField(max_length=150, required=False,
                                            label="City (as customer typed)")
    special_instructions = forms.CharField(max_length=250, required=False)
    shipment_type = forms.CharField(max_length=30, required=False)
    tracking_number = forms.CharField(max_length=100, required=False,
                                      help_text="Manual couriers only: CN given by the courier")

    def __init__(self, *args, provider=None, **kwargs):
        super().__init__(*args, **kwargs)
        p = provider
        if self.is_bound and self.data.get("provider"):
            p = CourierProvider.objects.filter(pk=self.data.get("provider")).first() or provider
        if p:
            self.fields["destination_city"].queryset = CourierCity.objects.filter(
                provider=p, is_active=True, allow_destination=True)
        self._style()

    def clean(self):
        data = super().clean()
        provider = data.get("provider")
        if provider:
            adapter = provider.get_adapter()
            if adapter.supports_cities and not data.get("destination_city"):
                self.add_error("destination_city", "Pick the destination city from the courier's list.")
            if not adapter.supports_api_booking and not data.get("tracking_number"):
                self.add_error("tracking_number", "Enter the tracking number for this manual courier.")
        return data


class ProviderForm(_Bootstrap, forms.ModelForm):
    adapter = forms.ChoiceField(choices=())

    class Meta:
        model = CourierProvider
        fields = ["name", "code", "adapter", "environment", "live_base_url", "sandbox_base_url",
                  "tracking_url_template", "webhook_base_url", "is_active", "is_default", "auto_book_enabled",
                  "auto_book_on_status", "auto_book_payment_methods", "default_weight_grams",
                  "default_shipment_type", "sort_order"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["adapter"].choices = adapter_choices()
        from Web.models import Order
        self.fields["auto_book_on_status"] = forms.ChoiceField(choices=Order.ORDER_STATUS)
        self._style()

    def clean_is_default(self):
        v = self.cleaned_data["is_default"]
        if v:
            CourierProvider.objects.exclude(pk=self.instance.pk).filter(is_default=True) \
                .update(is_default=False)
        return v


class CredentialForm(_Bootstrap, forms.ModelForm):
    api_key = forms.CharField(required=False, widget=forms.PasswordInput(render_value=False),
                              help_text="Leave empty to keep the saved value")
    api_password = forms.CharField(required=False, widget=forms.PasswordInput(render_value=False),
                                   help_text="Leave empty to keep the saved value")
    extra_secret = forms.CharField(required=False, widget=forms.PasswordInput(render_value=False),
                                   label="Other secret", help_text="Leave empty to keep the saved value")

    class Meta:
        model = CourierCredential
        fields = ["label", "environment", "api_key", "api_password", "account_number", "extra",
                  "extra_secret", "webhook_token", "is_active"]
        widgets = {"extra": forms.Textarea(attrs={"rows": 2})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["webhook_token"].required = False
        self.fields["webhook_token"].widget.attrs["autocomplete"] = "off"
        self._style()

    def clean_webhook_token(self):
        token = (self.cleaned_data.get("webhook_token") or "").strip().strip("/")
        if not token:  # empty = keep the current link (or create one for a new credential)
            return self.instance.webhook_token if self.instance.pk else \
                CourierCredential._meta.get_field("webhook_token").default()
        if not re.fullmatch(r"[A-Za-z0-9_-]{16,64}", token):
            raise forms.ValidationError("Use 16 to 64 characters: letters, digits, - or _ only.")
        if CourierCredential.objects.exclude(pk=self.instance.pk).filter(webhook_token=token).exists():
            raise forms.ValidationError("This token is already used by another credential.")
        return token

    def save(self, commit=True):
        obj = super().save(commit=False)
        for f in ("api_key", "api_password", "extra_secret"):
            new = self.cleaned_data.get(f)
            if not new and self.instance.pk:
                # keep the stored secret
                setattr(obj, f, CourierCredential.objects.get(pk=self.instance.pk).__dict__[f])
        if commit:
            obj.save()
        return obj


class ShipperForm(_Bootstrap, forms.ModelForm):
    class Meta:
        model = ShipperProfile
        fields = ["label", "contact_name", "phone", "email", "address", "city",
                  "return_same_as_pickup", "return_contact_name", "return_phone", "return_address",
                  "return_city", "is_default"]
        widgets = {"address": forms.Textarea(attrs={"rows": 2}),
                   "return_address": forms.Textarea(attrs={"rows": 2})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._style()

    def clean_is_default(self):
        v = self.cleaned_data["is_default"]
        if v:
            ShipperProfile.objects.exclude(pk=self.instance.pk).filter(is_default=True) \
                .update(is_default=False)
        return v


class StatusMappingForm(_Bootstrap, forms.ModelForm):
    class Meta:
        model = StatusMapping
        fields = ["provider", "courier_status", "match_type", "shipment_status", "order_status",
                  "notify_customer", "priority"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from Web.models import Order
        self.fields["order_status"] = forms.ChoiceField(
            choices=[("", "— don't change order —")] + list(Order.ORDER_STATUS), required=False)
        self._style()


class ManualStatusForm(_Bootstrap, forms.Form):
    status = forms.ChoiceField(choices=[c for c in ShipmentStatus.choices
                                        if c[0] not in ("booking_failed",)])
    note = forms.CharField(max_length=300, required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._style()


# ---------------------------------------------------------------------------
# Weight-based shipping rates
# ---------------------------------------------------------------------------
from django.forms import inlineformset_factory  # noqa: E402

from .models import ShippingTariff, TariffSlab  # noqa: E402


class TariffForm(_Bootstrap, forms.ModelForm):
    class Meta:
        model = ShippingTariff
        fields = ["name", "provider", "service_type", "origin_city", "origin_province", "is_active", "is_default",
                  "extra_step_grams", "extra_within_city", "extra_same_province", "extra_other_province", "notes"]
        labels = {"extra_step_grams": "Extra step (grams)", "extra_within_city": "Extra per step - within city",
                  "extra_same_province": "Extra per step - Zone A", "extra_other_province": "Extra per step - Zone B"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._style()

    def clean_is_default(self):
        v = self.cleaned_data["is_default"]
        if v:
            ShippingTariff.objects.exclude(pk=self.instance.pk).filter(is_default=True).update(is_default=False)
        return v

    def clean_origin_province(self):
        from .tariffs import normalize_province, province_label
        v = (self.cleaned_data.get("origin_province") or "").strip()
        if v and not normalize_province(v):
            raise forms.ValidationError("Unknown province. Use e.g. Punjab, Sindh, KPK, Balochistan, Islamabad.")
        return province_label(normalize_province(v)) if v else ""


class SlabForm(forms.ModelForm):
    class Meta:
        model = TariffSlab
        fields = ["max_grams", "within_city", "same_province", "other_province"]
        widgets = {f: forms.NumberInput(attrs={"class": "form-control form-control-sm", "min": "0",
                                                "step": "1" if f == "max_grams" else "0.01"})
                   for f in ["max_grams", "within_city", "same_province", "other_province"]}


class _SlabFormSet(forms.BaseInlineFormSet):
    def clean(self):
        super().clean()
        seen = set()
        for f in self.forms:
            if not getattr(f, "cleaned_data", None) or f.cleaned_data.get("DELETE"):
                continue
            g = f.cleaned_data.get("max_grams")
            if g in seen:
                raise forms.ValidationError(f"Two rows have the same weight limit ({g} g).")
            if g is not None:
                seen.add(g)
        if not seen:
            raise forms.ValidationError("Add at least one weight slab.")


SlabFormSet = inlineformset_factory(ShippingTariff, TariffSlab, form=SlabForm, formset=_SlabFormSet,
                                    extra=2, can_delete=True)
