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


import re

from django import forms

from .models import TopbarItem

_ICON = re.compile(r"^bi-[a-z0-9-]+$")


class TopbarItemForm(forms.ModelForm):
    """Validation for the topbar editor (a plain Django form — the admin is not involved)."""

    class Meta:
        model = TopbarItem
        fields = [
            "side", "kind", "label", "icon", "href",
            "open_in_new_tab", "visible_from", "is_active",
        ]

    def clean_label(self):
        return (self.cleaned_data.get("label") or "").strip()

    def clean_icon(self):
        icon = (self.cleaned_data.get("icon") or "").strip().lower()
        icon = re.sub(r"^bi\s+", "", icon)          # "bi bi-truck" -> "bi-truck"
        if icon and not icon.startswith("bi-"):
            icon = f"bi-{icon}"                      # "truck"      -> "bi-truck"
        if icon and not _ICON.match(icon):
            raise forms.ValidationError("Icon names look like bi-truck (letters, numbers and dashes).")
        return icon

    def clean_href(self):
        href = (self.cleaned_data.get("href") or "").strip()
        if href.lower().startswith("tel:"):
            href = "tel:" + re.sub(r"[^\d+]", "", href[4:])   # tel:+92 309-090 0926 -> tel:+923090900926
        return href

    def clean(self):
        cleaned = super().clean()
        kind = cleaned.get("kind")

        if kind in ("text", "link") and not cleaned.get("label"):
            self.add_error("label", "Enter the text to show.")

        if kind == "link" and not cleaned.get("href"):
            self.add_error("href", "Enter where the link should go.")

        # Drop whatever the chosen type doesn't use, so nothing stale is saved
        if kind == "divider":
            cleaned["label"] = ""
            cleaned["icon"] = ""
        if kind in ("text", "divider"):
            cleaned["href"] = ""
            cleaned["open_in_new_tab"] = False

        return cleaned