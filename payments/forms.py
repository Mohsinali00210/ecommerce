from django import forms

from .models import PaymentGateway


class GatewayForm(forms.ModelForm):
    api_key = forms.CharField(required=False, widget=forms.PasswordInput(render_value=False),
                              help_text="Leave empty to keep the saved value")
    secret_key = forms.CharField(required=False, widget=forms.PasswordInput(render_value=False),
                                 help_text="Leave empty to keep the saved value")
    webhook_secret = forms.CharField(required=False, widget=forms.PasswordInput(render_value=False),
                                     help_text="Leave empty to keep the saved value")

    class Meta:
        model = PaymentGateway
        fields = ["name", "environment", "api_key", "secret_key", "webhook_secret", "sandbox_base_url",
                  "live_base_url", "is_active"]

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        for f in self.fields.values():
            f.widget.attrs.setdefault("class", "form-check-input" if isinstance(f.widget, forms.CheckboxInput)
                                      else "form-select" if isinstance(f.widget, forms.Select) else "form-control")

    def save(self, commit=True):
        obj = super().save(commit=False)
        if self.instance.pk:
            stored = PaymentGateway.objects.get(pk=self.instance.pk)
            for f in ("api_key", "secret_key", "webhook_secret"):
                if not self.cleaned_data.get(f):
                    setattr(obj, f, getattr(stored, f))
        if commit:
            obj.save()
        return obj
