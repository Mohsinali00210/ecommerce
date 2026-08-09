from django import forms
from django.contrib.auth import get_user_model

User = get_user_model()

GENDER_CHOICES = [
    ("", "Prefer not to say"),
    ("male", "Male"),
    ("female", "Female"),
    ("other", "Other"),
]


class ProfileEditForm(forms.ModelForm):
    gender = forms.ChoiceField(choices=GENDER_CHOICES, required=False)

    class Meta:
        model = User
        fields = ["full_name", "email", "mobile", "dob", "gender", "avatar"]
        widgets = {
            "dob": forms.DateInput(attrs={"type": "date"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            if isinstance(field.widget, (forms.Select,)):
                css_class = "form-select"
            elif isinstance(field.widget, forms.FileInput):
                css_class = "form-control"
            else:
                css_class = "form-control"
            existing = field.widget.attrs.get("class", "")
            field.widget.attrs["class"] = f"{existing} {css_class}".strip()

    def clean_email(self):
        email = (self.cleaned_data.get("email") or "").strip().lower()
        if email:
            exists = (
                User.objects.filter(email__iexact=email)
                .exclude(pk=self.instance.pk)
                .exists()
            )
            if exists:
                raise forms.ValidationError("This email is already in use.")
        return email

    def clean_mobile(self):
        mobile = (self.cleaned_data.get("mobile") or "").strip()
        if mobile:
            exists = (
                User.objects.filter(mobile=mobile)
                .exclude(pk=self.instance.pk)
                .exists()
            )
            if exists:
                raise forms.ValidationError("This mobile number is already in use.")
        return mobile

from accounts.models import Address
class AddressForm(forms.ModelForm):
    class Meta:
        model = Address
        fields = [
            "address_type", "full_name", "phone", "street_address",
            "city", "state", "country", "postal_code", "is_default",
        ]
        widgets = {
            "street_address": forms.Textarea(attrs={"rows": 2}),
        }
 
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            if name == "is_default":
                field.widget.attrs["class"] = "form-check-input"
            elif isinstance(field.widget, forms.Select):
                field.widget.attrs["class"] = "form-select"
            else:
                field.widget.attrs["class"] = "form-control"