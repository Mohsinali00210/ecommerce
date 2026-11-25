"""Storefront content managed from the admin panel, and SEO / search-engine settings."""
import secrets

from django.conf import settings
from django.core.cache import cache
from django.db import models

from couriers.crypto import EncryptedTextField

SEO_CACHE_KEY = "seo_settings_v1"
FEATURES_CACHE_KEY = "home_features_v1"


class HomeFeature(models.Model):
    """One tile of the home page trust bar (Free Shipping, Cash on Delivery...)."""
    icon = models.CharField(max_length=60, default="bi-check-circle",
                            help_text="Bootstrap icon name, e.g. bi-truck (see icons.getbootstrap.com)")
    title = models.CharField(max_length=60)
    subtitle = models.CharField(max_length=120, blank=True,
                                help_text="Use {threshold} to show the free-shipping amount, e.g. "
                                          "'On orders over PKR {threshold}'")
    link_url = models.CharField(max_length=300, blank=True,
                                help_text="Optional page to open on click, e.g. /Contact/")
    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True, verbose_name="Show")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["sort_order", "id"]

    def __str__(self):
        return self.title

    def save(self, *a, **kw):
        super().save(*a, **kw)
        cache.delete(FEATURES_CACHE_KEY)

    def delete(self, *a, **kw):
        r = super().delete(*a, **kw)
        cache.delete(FEATURES_CACHE_KEY)
        return r

    @classmethod
    def active(cls):
        rows = cache.get(FEATURES_CACHE_KEY)
        if rows is None:
            rows = list(cls.objects.filter(is_active=True))
            cache.set(FEATURES_CACHE_KEY, rows, 300)
        return rows


def _indexnow_key():
    return secrets.token_hex(16)


class SeoSettings(models.Model):
    """Single row of SEO settings, edited in Admin > Storefront > SEO & search engines."""

    # --- Basics -------------------------------------------------------------
    site_address = models.URLField(
        default="https://shanzee.com", blank=True,
        help_text="Public address used in the sitemap, canonical links, Google feed and IndexNow, "
                  "e.g. https://shanzee.com (empty = SITE_URL from .env)")
    site_name = models.CharField(max_length=80, default="Shan Zee")
    home_title = models.CharField(max_length=70, default="Shan Zee — Considered Goods, Well Made",
                                  help_text="Home page title (aim for 50-60 characters)")
    title_suffix = models.CharField(max_length=40, default=" — Shan Zee", blank=True,
                                    help_text="Added after every other page title")
    default_description = models.CharField(
        max_length=170, blank=True,
        default="Shan Zee — considered goods, delivered across Pakistan. Free shipping, "
                "cash on delivery and easy returns.",
        help_text="Used when a page has no description of its own (aim for 120-160 characters)")
    default_share_image = models.ImageField(upload_to="seo/", blank=True,
                                            help_text="Picture shown when a link is shared (1200x630 px)")
    twitter_handle = models.CharField(max_length=40, blank=True, help_text="e.g. @shanzee")

    # --- Business details (Google rich results / knowledge panel) ------------
    logo = models.ImageField(upload_to="seo/", blank=True, help_text="Square logo, at least 112x112 px")
    phone = models.CharField(max_length=30, blank=True, help_text="e.g. +92 300 1234567")
    email = models.EmailField(blank=True)
    street_address = models.CharField(max_length=200, blank=True)
    city = models.CharField(max_length=80, blank=True)
    region = models.CharField(max_length=80, blank=True, help_text="Province, e.g. Punjab")
    postal_code = models.CharField(max_length=20, blank=True)
    country = models.CharField(max_length=2, default="PK", help_text="2-letter country code")
    social_links = models.TextField(blank=True, help_text="One profile URL per line (Facebook, Instagram, TikTok...)")
    return_days = models.PositiveSmallIntegerField(default=7, help_text="Return window shown to Google (days)")

    # --- Search engines -----------------------------------------------------
    google_site_verification = models.CharField(
        max_length=120, blank=True,
        help_text="Google Search Console 'HTML tag' code: only the content=\"...\" value")
    bing_site_verification = models.CharField(
        max_length=120, blank=True, help_text="Bing Webmaster Tools msvalidate.01 content value")
    google_analytics_id = models.CharField(max_length=30, blank=True, help_text="GA4 measurement ID, e.g. G-XXXXXXX")
    hide_from_search_engines = models.BooleanField(
        default=False, help_text="Ask search engines not to index the site (use on a test/staging copy only)")
    robots_extra = models.TextField(blank=True, help_text="Extra robots.txt lines (advanced)")

    # --- Sitemap ------------------------------------------------------------
    sitemap_builtin_pages = models.JSONField(
        default=list, blank=True,
        help_text="Built-in pages listed in sitemap-pages.xml (empty = all of them)")
    sitemap_extra_pages = models.TextField(
        blank=True,
        help_text="Extra pages for sitemap-pages.xml, one per line: /path/  or  /path/ | 0.8 | weekly")

    # --- Instant indexing ---------------------------------------------------
    indexnow_enabled = models.BooleanField(
        default=False, help_text="Tell Bing, Yandex, Seznam, Naver... instantly when products/posts change")
    indexnow_key = models.CharField(max_length=64, default=_indexnow_key,
                                    help_text="Public key served at /<key>.txt")
    google_indexing_enabled = models.BooleanField(
        default=False, help_text="Send changed URLs to the Google Indexing API (service account needed)")
    google_service_account = EncryptedTextField(
        blank=True, help_text="Service account JSON key (stored encrypted)")

    # --- Google Merchant Center ----------------------------------------------
    merchant_feed_enabled = models.BooleanField(default=True,
                                                help_text="Publish the product feed for Google Merchant Center")
    merchant_default_brand = models.CharField(max_length=80, blank=True, default="Shan Zee",
                                              help_text="Brand used when a product has none")
    merchant_google_category = models.CharField(
        max_length=200, blank=True,
        help_text="Default Google product category, e.g. 'Apparel & Accessories' or its number")
    # Merchant API: push products straight to Merchant Center (instead of / as well as the feed)
    merchant_api_enabled = models.BooleanField(
        default=False, help_text="Send products to Google Merchant Center through the Merchant API")
    merchant_auto_sync = models.BooleanField(
        default=True, help_text="Send a product as soon as it is saved (and remove it when hidden)")
    merchant_account_id = models.CharField(max_length=30, blank=True,
                                           help_text="Merchant Center account ID (number at the top of Merchant Center)")
    merchant_data_source_id = models.CharField(
        max_length=30, blank=True, help_text="ID of an API data source (Merchant Center > Settings > Data sources)")
    merchant_feed_label = models.CharField(max_length=20, default="PK", blank=True,
                                           help_text="Feed label, usually the country code: PK")
    merchant_content_language = models.CharField(max_length=5, default="en", blank=True)

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = verbose_name_plural = "SEO settings"

    def __str__(self):
        return "SEO settings"

    def save(self, *a, **kw):
        self.pk = 1
        super().save(*a, **kw)
        cache.delete(SEO_CACHE_KEY)

    @classmethod
    def get(cls):
        obj = cache.get(SEO_CACHE_KEY)
        if obj is None:
            obj, _ = cls.objects.get_or_create(pk=1)
            cache.set(SEO_CACHE_KEY, obj, 300)
        return obj

    def social_list(self):
        return [l.strip() for l in (self.social_links or "").splitlines() if l.strip().startswith("http")]


class IndexingLog(models.Model):
    ENGINES = [("indexnow", "IndexNow (Bing & others)"), ("google", "Google Indexing API"),
               ("merchant", "Google Merchant API")]
    engine = models.CharField(max_length=10, choices=ENGINES)
    action = models.CharField(max_length=20, default="updated")
    urls = models.JSONField(default=list)
    ok = models.BooleanField(default=False)
    status_code = models.PositiveIntegerField(null=True, blank=True)
    message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                   on_delete=models.SET_NULL, related_name="+")

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.engine} {self.action} {len(self.urls)} url(s)"


class MerchantProduct(models.Model):
    """Last Merchant API result for each product."""
    product = models.OneToOneField("products.Product", on_delete=models.CASCADE, related_name="merchant_status")
    offer_id = models.CharField(max_length=60)
    status = models.CharField(max_length=10, default="pending")  # pending / synced / removed / error
    message = models.TextField(blank=True)
    synced_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self):
        return f"{self.offer_id} ({self.status})"
