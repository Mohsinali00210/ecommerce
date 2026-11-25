from django import forms

from .models import PaymentGateway

SECRET_FIELDS = ("api_key", "secret_key", "webhook_secret")


class GatewayForm(forms.ModelForm):
    """Settings for one gateway. Labels and extra fields come from its adapter
    (payments/gateways/<code>.py). Secrets are write-only: empty = keep the saved value."""
    api_key = forms.CharField(required=False, widget=forms.PasswordInput(render_value=False),
                              help_text="Leave empty to keep the saved value")
    secret_key = forms.CharField(required=False, widget=forms.PasswordInput(render_value=False),
                                 help_text="Leave empty to keep the saved value")
    webhook_secret = forms.CharField(required=False, widget=forms.PasswordInput(render_value=False),
                                     help_text="Leave empty to keep the saved value")

    class Meta:
        model = PaymentGateway
        fields = ["name", "checkout_label", "environment", "api_key", "secret_key", "webhook_secret",
                  "sandbox_base_url", "live_base_url", "sort_order", "is_active"]

    def __init__(self, *a, adapter_cls=None, **kw):
        super().__init__(*a, **kw)
        self.adapter_cls = adapter_cls
        if adapter_cls:
            for f, label in adapter_cls.credential_labels.items():
                if f in self.fields:
                    self.fields[f].label = label
                    stored = bool(self.instance.pk and getattr(self.instance, f))
                    self.fields[f].help_text = ("Saved - leave empty to keep it" if stored
                                                else ("Required" if f in adapter_cls.required_fields else "Optional"))
            if not adapter_cls.needs_base_url:
                for f in ("sandbox_base_url", "live_base_url"):
                    self.fields.pop(f, None)
            if set(adapter_cls.credential_labels.values()) == {"Not used"}:
                for f in SECRET_FIELDS:
                    self.fields.pop(f, None)
            self.fields["checkout_label"].widget.attrs["placeholder"] = adapter_cls.checkout_label
            extra = self.instance.extra or {}
            for key, (label, help_text, default) in adapter_cls.extra_fields.items():
                self.fields[f"extra__{key}"] = forms.CharField(
                    label=label, help_text=help_text, required=False, initial=extra.get(key, default))
        for f in self.fields.values():
            f.widget.attrs.setdefault("class", "form-check-input" if isinstance(f.widget, forms.CheckboxInput)
                                      else "form-select" if isinstance(f.widget, forms.Select) else "form-control")

    def clean(self):
        data = super().clean()
        if data.get("is_active") and self.adapter_cls:
            missing = []
            for f in self.adapter_cls.required_fields:
                if not (data.get(f) or (self.instance.pk and getattr(self.instance, f))):
                    missing.append(self.adapter_cls.credential_labels.get(f, f))
            if self.adapter_cls.needs_base_url:
                env = data.get("environment")
                url = data.get("live_base_url") if env == "live" else data.get("sandbox_base_url")
                if not url:
                    missing.append(f"{'Live' if env == 'live' else 'Sandbox'} base URL")
            if missing:
                raise forms.ValidationError("To switch this gateway on, fill in: " + ", ".join(missing) + ".")
            if self.adapter_cls.sandbox_only and data.get("environment") == "live":
                self.add_error("environment", "The test gateway can only run in sandbox mode.")
        return data

    def save(self, commit=True):
        obj = super().save(commit=False)
        if self.instance.pk:
            stored = PaymentGateway.objects.get(pk=self.instance.pk)
            for f in SECRET_FIELDS:
                if not self.cleaned_data.get(f):
                    setattr(obj, f, getattr(stored, f))
        if self.adapter_cls:
            extra = dict(obj.extra or {})
            for key in self.adapter_cls.extra_fields:
                extra[key] = (self.cleaned_data.get(f"extra__{key}") or "").strip()
            obj.extra = extra
        if commit:
            obj.save()
        return obj


class PayoutMethodForm(forms.ModelForm):
    api_key = forms.CharField(required=False, widget=forms.PasswordInput(render_value=False),
                              label="API key / Stripe secret key", help_text="Leave empty to keep the saved value")
    api_secret = forms.CharField(required=False, widget=forms.PasswordInput(render_value=False),
                                 label="Signing secret", help_text="Generic payout API only. Empty = keep saved value")

    class Meta:
        from .models import PayoutMethod
        model = PayoutMethod
        fields = ["name", "is_enabled", "fee_fixed", "fee_percent", "fee_min", "fee_max", "min_amount",
                  "max_amount", "processing_time", "mode", "provider", "environment", "api_url", "api_key",
                  "api_secret", "sort_order"]

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        for f in self.fields.values():
            f.widget.attrs.setdefault("class", "form-check-input" if isinstance(f.widget, forms.CheckboxInput)
                                      else "form-select" if isinstance(f.widget, forms.Select) else "form-control")

    def clean(self):
        data = super().clean()
        if data.get("mode") == "api":
            p = data.get("provider")
            if not p:
                self.add_error("provider", "Choose how automatic payouts are sent.")
            elif p == "test" and data.get("environment") != "sandbox":
                self.add_error("environment", "The test provider only works in sandbox mode.")
            elif p == "http" and not data.get("api_url"):
                self.add_error("api_url", "Enter your payout API URL.")
            elif p == "stripe" and not (data.get("api_key") or (self.instance.pk and self.instance.api_key)):
                self.add_error("api_key", "Enter the Stripe secret key.")
        for f in ("fee_fixed", "fee_percent", "fee_min", "min_amount"):
            if data.get(f) is not None and data[f] < 0:
                self.add_error(f, "Can't be negative.")
        if data.get("fee_percent") is not None and data["fee_percent"] > 100:
            self.add_error("fee_percent", "Can't be more than 100%.")
        return data

    def save(self, commit=True):
        obj = super().save(commit=False)
        if self.instance.pk:
            from .models import PayoutMethod
            stored = PayoutMethod.objects.get(pk=self.instance.pk)
            for f in ("api_key", "api_secret"):
                if not self.cleaned_data.get(f):
                    setattr(obj, f, getattr(stored, f))
        if commit:
            obj.save()
        return obj
