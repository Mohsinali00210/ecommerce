"""Admin panel pages: Storefront > Home page features, Storefront > SEO & search engines.
Access is enforced by accounts.rbac (/Adminpanel/Storefront/ -> view_catalog / manage_marketing)."""
import json
import re

from django import forms
from django.contrib import messages
from django.forms import modelformset_factory
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST
from django_ratelimit.decorators import ratelimit

from accounts.error_logging import security_event
from adminpanel import shipping
from payments.validators import validate_image

from . import seo
from .indexing import IndexingError, google_submit, indexnow_submit, test_google_credentials
from .models import HomeFeature, IndexingLog, SeoSettings
from .sitemaps import BUILTIN_PAGES, page_entries

ICON_CHOICES = ["bi-truck", "bi-cash-coin", "bi-arrow-repeat", "bi-shield-check", "bi-shield-lock",
                "bi-credit-card", "bi-wallet2", "bi-gift", "bi-headset", "bi-telephone", "bi-whatsapp",
                "bi-box-seam", "bi-award", "bi-patch-check", "bi-star", "bi-heart", "bi-clock-history",
                "bi-lightning-charge", "bi-geo-alt", "bi-globe", "bi-tag", "bi-percent", "bi-recycle",
                "bi-hand-thumbs-up", "bi-emoji-smile", "bi-bag-check", "bi-stars", "bi-gem"]


def _style(form):
    for f in form.fields.values():
        w = f.widget
        if isinstance(w, forms.CheckboxInput):
            w.attrs.setdefault("class", "form-check-input")
        elif isinstance(w, forms.ClearableFileInput):
            w.attrs.setdefault("class", "form-control")
        else:
            w.attrs.setdefault("class", "form-control form-control-sm" if not isinstance(w, forms.Textarea)
                               else "form-control")


# ---------------------------------------------------------------------------
# Home page features (trust bar)
# ---------------------------------------------------------------------------
class HomeFeatureForm(forms.ModelForm):
    class Meta:
        model = HomeFeature
        fields = ["icon", "title", "subtitle", "link_url", "sort_order", "is_active"]
        widgets = {"icon": forms.TextInput(attrs={"list": "szIconList"})}

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        _style(self)
        self.fields["title"].required = False  # blank extra rows are ignored

    def clean_icon(self):
        icon = (self.cleaned_data.get("icon") or "").strip()
        if icon and not icon.startswith("bi-"):
            icon = "bi-" + icon
        if icon and not re.fullmatch(r"bi-[a-z0-9-]{1,50}", icon):
            raise forms.ValidationError("Use a Bootstrap icon name like bi-truck.")
        return icon or "bi-check-circle"

    def clean_link_url(self):
        url = (self.cleaned_data.get("link_url") or "").strip()
        if url and not (url.startswith("/") or url.startswith("https://") or url.startswith("http://")):
            raise forms.ValidationError("Start with / for a page of this site, or with https://")
        if url.lower().startswith("javascript:"):
            raise forms.ValidationError("Not a valid link.")
        return url

    def clean(self):
        data = super().clean()
        if self.has_changed() and not data.get("title") and not data.get("DELETE"):
            self.add_error("title", "Enter a title.")
        return data


FeatureFormSet = modelformset_factory(HomeFeature, form=HomeFeatureForm, extra=1, can_delete=True)


def home_features(request):
    qs = HomeFeature.objects.all()
    formset = FeatureFormSet(request.POST or None, queryset=qs)
    if request.method == "POST":
        if formset.is_valid():
            for f in formset.forms:
                if not f.has_changed() and not f.instance.pk:
                    continue
                if f.cleaned_data.get("DELETE"):
                    if f.instance.pk:
                        f.instance.delete()
                    continue
                if f.cleaned_data.get("title"):
                    f.save()
            messages.success(request, "Home page features saved.")
            return redirect("storefront_home_features")
        messages.error(request, "Please fix the highlighted fields.")
    rules = shipping.rules()
    return render(request, "storefront/admin/home_features.html", {
        "formset": formset, "icons": ICON_CHOICES,
        "threshold": rules["free_threshold"] if rules["free_enabled"] else None,
    })


# ---------------------------------------------------------------------------
# SEO & search engines
# ---------------------------------------------------------------------------
VERIFY_RE = re.compile(r'content\s*=\s*["\']([^"\']+)["\']', re.I)


class SeoForm(forms.ModelForm):
    google_service_account = forms.CharField(
        required=False, widget=forms.Textarea(attrs={"rows": 3, "placeholder": "Paste the JSON key to replace it"}),
        help_text="Leave empty to keep the saved key")
    clear_google_key = forms.BooleanField(required=False, label="Remove the saved Google key")
    sitemap_builtin_pages = forms.MultipleChoiceField(
        required=False, widget=forms.CheckboxSelectMultiple, label="Built-in pages",
        choices=[(k, v[1]) for k, v in BUILTIN_PAGES.items()])

    class Meta:
        model = SeoSettings
        fields = ["site_address", "site_name", "home_title", "title_suffix", "default_description", "default_share_image",
                  "twitter_handle", "logo", "phone", "email", "street_address", "city", "region", "postal_code",
                  "country", "social_links", "return_days",
                  "google_site_verification", "bing_site_verification", "google_analytics_id",
                  "hide_from_search_engines", "robots_extra", "sitemap_builtin_pages", "sitemap_extra_pages",
                  "indexnow_enabled", "indexnow_key", "google_indexing_enabled", "google_service_account",
                  "merchant_feed_enabled", "merchant_default_brand", "merchant_google_category"]
        widgets = {"social_links": forms.Textarea(attrs={"rows": 3}),
                   "robots_extra": forms.Textarea(attrs={"rows": 2}),
                   "sitemap_extra_pages": forms.Textarea(attrs={
                       "rows": 4, "placeholder": "/about-us/\n/return-policy/ | 0.4 | monthly\n/search-products/?category=3 | 0.7"}),
                   "default_description": forms.Textarea(attrs={"rows": 2})}

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.initial["google_service_account"] = ""
        if not self.instance.sitemap_builtin_pages:  # empty = all
            self.initial["sitemap_builtin_pages"] = list(BUILTIN_PAGES)
        _style(self)
        self.fields["sitemap_builtin_pages"].widget.attrs["class"] = "form-check-input"
        self.fields["home_title"].widget.attrs["data-counter"] = "60"
        self.fields["default_description"].widget.attrs["data-counter"] = "160"
        self.fields["google_site_verification"].widget.attrs["placeholder"] = \
            "Paste the code, or the whole <meta name=\"google-site-verification\" ...> tag"
        self.fields["bing_site_verification"].widget.attrs["placeholder"] = \
            "Paste the code, or the whole <meta name=\"msvalidate.01\" ...> tag"

    def _verification(self, name):
        v = (self.cleaned_data.get(name) or "").strip()
        m = VERIFY_RE.search(v)  # the whole <meta ...> tag was pasted
        v = m.group(1) if m else v
        if v and not re.fullmatch(r"[A-Za-z0-9_\-=.]{6,120}", v):
            raise forms.ValidationError("Paste only the code from the meta tag's content=\"...\" value.")
        return v

    def clean_google_site_verification(self):
        return self._verification("google_site_verification")

    def clean_bing_site_verification(self):
        return self._verification("bing_site_verification")

    def clean_google_analytics_id(self):
        v = (self.cleaned_data.get("google_analytics_id") or "").strip().upper()
        if v and not re.fullmatch(r"G-[A-Z0-9]{4,20}", v):
            raise forms.ValidationError("A GA4 measurement ID looks like G-XXXXXXXXXX.")
        return v

    def clean_twitter_handle(self):
        v = (self.cleaned_data.get("twitter_handle") or "").strip()
        if v and not v.startswith("@"):
            v = "@" + v
        if v and not re.fullmatch(r"@[A-Za-z0-9_]{1,30}", v):
            raise forms.ValidationError("Use the handle only, e.g. @shanzee")
        return v

    def clean_indexnow_key(self):
        v = (self.cleaned_data.get("indexnow_key") or "").strip()
        if not re.fullmatch(r"[A-Za-z0-9-]{8,128}", v):
            raise forms.ValidationError("8 to 128 characters: letters, digits and - only.")
        return v

    def clean_sitemap_builtin_pages(self):
        chosen = self.cleaned_data.get("sitemap_builtin_pages") or []
        if not chosen:
            raise forms.ValidationError("Keep at least the home page in the sitemap.")
        return chosen

    def clean_sitemap_extra_pages(self):
        from .sitemaps import parse_extra_pages
        text = "\n".join(l.rstrip() for l in (self.cleaned_data.get("sitemap_extra_pages") or "").splitlines()
                         if l.strip())
        try:
            parse_extra_pages(text)
        except ValueError as exc:
            raise forms.ValidationError(str(exc))
        return text

    def clean_site_address(self):
        v = (self.cleaned_data.get("site_address") or "").strip().rstrip("/")
        if v and not re.fullmatch(r"https?://[A-Za-z0-9.-]+(:\d+)?", v):
            raise forms.ValidationError("Only the address, e.g. https://shanzee.com (no page path).")
        return v

    def clean_country(self):
        return (self.cleaned_data.get("country") or "PK").strip().upper()[:2]

    def clean_social_links(self):
        lines = [l.strip() for l in (self.cleaned_data.get("social_links") or "").splitlines() if l.strip()]
        for l in lines:
            if not l.startswith("https://"):
                raise forms.ValidationError(f"Each line must be a full https:// link ({l[:40]}).")
        return "\n".join(lines)

    def clean_robots_extra(self):
        v = self.cleaned_data.get("robots_extra") or ""
        ok = re.compile(r"^\s*(#.*|(User-agent|Disallow|Allow|Crawl-delay|Sitemap)\s*:.*)?\s*$", re.I)
        for line in v.splitlines():
            if not ok.match(line):
                raise forms.ValidationError(f"Not a robots.txt rule: {line[:60]}")
        return v

    def _image(self, name):
        f = self.cleaned_data.get(name)
        if f and hasattr(f, "content_type"):  # a newly uploaded file
            try:
                validate_image(f)
            except ValueError as exc:
                raise forms.ValidationError(str(exc))
        return f

    def clean_logo(self):
        return self._image("logo")

    def clean_default_share_image(self):
        return self._image("default_share_image")

    def clean_google_service_account(self):
        raw = (self.cleaned_data.get("google_service_account") or "").strip()
        if raw:
            try:
                from .indexing import parse_service_account
                parse_service_account(raw)
            except IndexingError as exc:
                raise forms.ValidationError(str(exc))
        return raw

    def clean(self):
        data = super().clean()
        if data.get("google_indexing_enabled") and not (
                data.get("google_service_account") or (self.instance.google_service_account
                                                         and not data.get("clear_google_key"))):
            self.add_error("google_indexing_enabled", "Add the service account JSON key first.")
        return data

    def save(self, commit=True):
        obj = super().save(commit=False)
        new = self.cleaned_data.get("google_service_account")
        if self.cleaned_data.get("clear_google_key"):
            obj.google_service_account = ""
        elif not new:
            obj.google_service_account = SeoSettings.objects.get(pk=1).google_service_account \
                if SeoSettings.objects.filter(pk=1).exists() else ""
        if commit:
            obj.save()
        return obj


def _service_email(raw):
    try:
        return json.loads(raw).get("client_email", "") if raw else ""
    except ValueError:
        return ""


def seo_settings(request):
    obj = SeoSettings.get()
    obj = SeoSettings.objects.get(pk=obj.pk)
    form = SeoForm(request.POST or None, request.FILES or None, instance=obj)
    if request.method == "POST":
        if form.is_valid():
            s = form.save()
            security_event("seo_settings_changed", request, severity="INFO",
                           hidden=s.hide_from_search_engines, indexnow=s.indexnow_enabled,
                           google_indexing=s.google_indexing_enabled)
            messages.success(request, "SEO settings saved.")
            return redirect("storefront_seo")
        messages.error(request, "Please fix the highlighted fields.")
    site = seo.site_url()
    checks = _checks(obj, site)
    return render(request, "storefront/admin/seo.html", {
        "form": form, "s": obj, "site": site, "checks": checks,
        "service_email": _service_email(obj.google_service_account),
        "logs": IndexingLog.objects.select_related("created_by")[:25],
        "links": {
            "sitemap": f"{site}/sitemap.xml", "robots": f"{site}/robots.txt",
            "indexnow_key": f"{site}/{obj.indexnow_key}.txt",
            "feed": f"{site}{reverse('storefront_merchant_feed')}",
        },
        "sitemap_pages": [(seo.site_url() + p, prio, freq, label) for p, prio, freq, label in page_entries()],
        "counts": {"products": seo.public_products().count(), "categories": seo.public_categories().count(),
                   "posts": seo.public_posts().count()},
    })


def _checks(s, site):
    """Plain-English checklist shown at the top of the SEO page."""
    out = []

    def add(ok, text, tip=""):
        out.append({"ok": ok, "text": text, "tip": tip})
    add(site.startswith("https://"), "Site address uses HTTPS",
        "Set 'Public site address' below to https://shanzee.com (search engines and Google Merchant need HTTPS).")
    add("127.0.0.1" not in site and "localhost" not in site, "Site address is your public domain",
        "The site address is a local address: set 'Public site address' below to https://shanzee.com.")
    add(not s.hide_from_search_engines, "Site is visible to search engines",
        "'Hide from search engines' is on: Google will drop the site.")
    add(bool(s.google_site_verification), "Google Search Console verification tag added")
    add(bool(s.bing_site_verification), "Bing Webmaster Tools verification tag added",
        "Or import the site from Google Search Console inside Bing Webmaster Tools.")
    add(bool(s.logo), "Store logo added (shown in Google results)")
    add(bool(s.default_share_image), "Share image added (WhatsApp / Facebook previews)")
    add(bool(s.phone and s.street_address and s.city), "Business phone and address added")
    add(s.indexnow_enabled, "IndexNow is on (Bing and others index changes within minutes)")
    return out


@require_POST
@ratelimit(key="user", rate="10/h", block=True)
def seo_tool(request, action):
    s = SeoSettings.get()
    if action == "submit-all":
        from .tasks import submit_all_urls
        submit_all_urls.delay(request.user.pk)
        messages.success(request, "All public pages are being sent to IndexNow. Results appear in the log below.")
    elif action in ("submit-url", "google-url"):
        url = (request.POST.get("url") or "").strip()
        if url.startswith("/"):
            url = seo.site_url() + url
        if not url.startswith(seo.site_url() + "/") and url != seo.site_url():
            messages.error(request, f"Only pages of {seo.site_url()} can be submitted.")
            return redirect("storefront_seo")
        rec = (indexnow_submit([url], user=request.user, force=True) if action == "submit-url"
               else google_submit([url], user=request.user, force=True))
        if rec is None:
            messages.error(request, "Nothing was sent. Is the site hidden from search engines?")
        elif rec.ok:
            messages.success(request, rec.message)
        else:
            messages.error(request, rec.message)
    elif action == "test-google":
        try:
            email = test_google_credentials(s.google_service_account)
            messages.success(request, f"Google accepted the key for {email}. Make sure this e-mail is an "
                                      "Owner of your property in Search Console.")
        except IndexingError as exc:
            messages.error(request, str(exc))
    elif action == "new-indexnow-key":
        from .models import _indexnow_key
        s = SeoSettings.objects.get(pk=s.pk)
        s.indexnow_key = _indexnow_key()
        s.save()
        messages.success(request, "New IndexNow key created.")
    else:
        messages.error(request, "Unknown action.")
    return redirect("storefront_seo")
