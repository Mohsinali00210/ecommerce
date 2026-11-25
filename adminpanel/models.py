from decimal import Decimal

from django.conf import settings
from django.core.cache import cache
from django.db import models

SETTINGS_CACHE_KEY = "store_settings_v1"

DEFAULT_EMAIL_STATUSES = ["processing", "booked", "shipped", "out_for_delivery", "delivered",
                          "cancelled", "return_in_transit", "returned"]


class StoreSettings(models.Model):
    """Single row of store-wide settings, edited in Admin > Settings."""

    # --- Payments -----------------------------------------------------------
    online_payments_enabled = models.BooleanField(
        default=False, help_text="Master switch. Off = no online payment method is offered or accepted.")
    cod_enabled = models.BooleanField(default=True, verbose_name="Cash on delivery")
    cod_max_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True,
                                         help_text="Hide COD above this order total (empty = no limit)")
    bank_transfer_enabled = models.BooleanField(default=False)
    bank_transfer_details = models.TextField(blank=True,
                                             help_text="Account title, bank, IBAN... shown to the customer")
    online_payment_timeout_minutes = models.PositiveIntegerField(
        default=60, help_text="Unpaid online orders are cancelled (stock released) after this long")

    # --- Shipping -------------------------------------------------------------
    free_shipping_enabled = models.BooleanField(
        default=True, help_text="Orders at or above the amount below ship free")
    free_shipping_threshold = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("3500.00"),
        help_text="Order amount (after discounts) that unlocks free shipping, Rs")
    max_shipping_charge = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("450.00"),
        help_text="Cart shipping is never more than this, Rs (0 = no cap)")
    weight_shipping_enabled = models.BooleanField(
        default=True, verbose_name="Weight-based shipping",
        help_text="Charge by parcel weight and destination zone using the default courier tariff "
                  "(Shipping > Shipping rates). Products with no weight keep their own flat charge.")

    # --- Customer emails ------------------------------------------------------
    email_order_confirmation = models.BooleanField(default=True)
    email_status_changes = models.BooleanField(default=True)
    email_statuses = models.JSONField(default=list, blank=True,
                                      help_text="Order statuses that send the customer an email")
    email_admin_new_order = models.BooleanField(default=True)

    # --- Backups --------------------------------------------------------------
    backup_schedule_enabled = models.BooleanField(default=False)
    backup_hour = models.PositiveSmallIntegerField(default=3, help_text="Hour of day (store time, 0-23)")
    backup_keep = models.PositiveSmallIntegerField(default=7, help_text="Scheduled backups to keep")
    backup_include_media = models.BooleanField(default=True)

    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                   related_name="+")

    class Meta:
        verbose_name = verbose_name_plural = "Store settings"

    def __str__(self):
        return "Store settings"

    def save(self, *args, **kwargs):
        self.pk = 1  # singleton
        if not self.email_statuses and self._state.adding:
            self.email_statuses = list(DEFAULT_EMAIL_STATUSES)
        super().save(*args, **kwargs)
        cache.delete(SETTINGS_CACHE_KEY)

    @classmethod
    def get(cls):
        obj = cache.get(SETTINGS_CACHE_KEY)
        if obj is None:
            obj, _ = cls.objects.get_or_create(pk=1, defaults={"email_statuses": list(DEFAULT_EMAIL_STATUSES)})
            cache.set(SETTINGS_CACHE_KEY, obj, 60)
        return obj

    # --- helpers ---------------------------------------------------------------
    def cod_allowed_for(self, total):
        if not self.cod_enabled:
            return False
        return self.cod_max_amount is None or Decimal(total or 0) <= self.cod_max_amount

    def free_shipping_for(self, amount):
        return bool(self.free_shipping_enabled and self.free_shipping_threshold is not None
                    and Decimal(amount or 0) >= self.free_shipping_threshold)

    def emails_status(self, status):
        return self.email_status_changes and status in (self.email_statuses or [])


class AdminSeen(models.Model):
    """When a staff member last opened each admin section (drives the unseen badges)."""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="admin_seen")
    section = models.CharField(max_length=40)
    seen_at = models.DateTimeField()

    class Meta:
        constraints = [models.UniqueConstraint(fields=["user", "section"], name="uniq_admin_seen")]


class Backup(models.Model):
    KIND_CHOICES = [("manual", "Manual"), ("scheduled", "Scheduled"), ("safety", "Before restore"),
                    ("uploaded", "Uploaded")]
    STATUS_CHOICES = [("running", "Creating…"), ("ready", "Ready"), ("failed", "Failed"),
                      ("restoring", "Restoring…"), ("restored", "Restored")]
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                   related_name="+")
    kind = models.CharField(max_length=10, choices=KIND_CHOICES, default="manual")
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="running")
    filename = models.CharField(max_length=200, blank=True)
    size_bytes = models.BigIntegerField(default=0)
    sha256 = models.CharField(max_length=64, blank=True)
    includes_media = models.BooleanField(default=True)
    record_count = models.PositiveIntegerField(default=0)
    note = models.CharField(max_length=255, blank=True)
    error = models.TextField(blank=True)
    restored_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.filename or f"Backup {self.pk}"

    @property
    def path(self):
        from .backups import backup_dir
        return backup_dir() / self.filename if self.filename else None
