from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.db import models
from django.utils import timezone
from django.utils.functional import LazyObject

from couriers.crypto import EncryptedTextField


class PrivateStorage(LazyObject):
    """Bank receipts are personal data: kept outside MEDIA_ROOT and only served
    through a view that checks the user (never by the public web server)."""

    def _setup(self):
        self._wrapped = FileSystemStorage(location=str(settings.PRIVATE_MEDIA_ROOT), base_url=None)


private_storage = PrivateStorage()


def get_private_storage():
    """Callable storage: migrations store this function's path, not the folder, so the
    private_media location (different on every machine) never creates new migrations."""
    return private_storage


class Environment(models.TextChoices):
    SANDBOX = "sandbox", "Sandbox / test"
    LIVE = "live", "Live / production"


class PaymentGateway(models.Model):
    code = models.SlugField(unique=True, help_text="Adapter name, e.g. safepay")
    name = models.CharField(max_length=100)
    environment = models.CharField(max_length=10, choices=Environment.choices, default=Environment.SANDBOX)
    api_key = EncryptedTextField(blank=True, help_text="Public / client API key")
    secret_key = EncryptedTextField(blank=True, help_text="Secret key (verifies payment signatures)")
    webhook_secret = EncryptedTextField(blank=True, help_text="Webhook signing secret")
    sandbox_base_url = models.URLField(blank=True)
    live_base_url = models.URLField(blank=True)
    is_active = models.BooleanField(default=False)
    checkout_label = models.CharField(max_length=80, blank=True,
                                      help_text="Name shown at checkout (empty = the gateway's default)")
    extra = models.JSONField(default=dict, blank=True, help_text="Gateway-specific, non-secret settings")
    sort_order = models.PositiveSmallIntegerField(default=10)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["sort_order", "name"]

    def __str__(self):
        return f"{self.name} ({self.get_environment_display()})"

    @property
    def base_url(self):
        return ((self.live_base_url if self.environment == Environment.LIVE else self.sandbox_base_url) or "").rstrip("/")

    def adapter_class(self):
        from .gateways import get_adapter
        return get_adapter(self.code)

    @property
    def configured(self):
        try:
            return self.adapter_class().is_configured(self)
        except LookupError:
            return False

    def adapter(self):
        return self.adapter_class()(self)

    def label(self):
        try:
            return self.checkout_label or self.adapter_class().checkout_label
        except LookupError:
            return self.checkout_label or self.name

    @classmethod
    def online_gateways(cls, user=None):
        """Active, configured gateways customers can pay with, in checkout order.
        The test gateway is only offered to staff (or to everyone while DEBUG is on)."""
        out = []
        staff = bool(user is not None and getattr(user, "is_staff", False))
        for g in cls.objects.filter(is_active=True):
            if not g.configured:
                continue
            if g.adapter_class().sandbox_only and not (settings.DEBUG or staff):
                continue
            out.append(g)
        return out

    @classmethod
    def online(cls, code=None, user=None):
        """An active, configured gateway (the given one, else the first), or None."""
        gws = cls.online_gateways(user=user)
        if code:
            return next((g for g in gws if g.code == code), None)
        return gws[0] if gws else None


class Payment(models.Model):
    METHOD_CHOICES = [("cod", "Cash on delivery"), ("bank", "Bank transfer"), ("online", "Card / wallet (online)")]
    STATUS_CHOICES = [("pending", "Pending"), ("paid", "Paid"), ("failed", "Failed"),
                      ("cancelled", "Cancelled"), ("expired", "Expired"), ("refunded", "Refunded")]

    order = models.ForeignKey("Web.Order", on_delete=models.CASCADE, related_name="payments")
    method = models.CharField(max_length=10, choices=METHOD_CHOICES)
    gateway = models.ForeignKey(PaymentGateway, on_delete=models.SET_NULL, null=True, blank=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, default="PKR")
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="pending", db_index=True)

    tracker = models.CharField(max_length=120, blank=True, db_index=True, help_text="Gateway session / tracker id")
    reference = models.CharField(max_length=120, blank=True, help_text="Gateway transaction reference")
    proof = models.FileField(storage=get_private_storage, upload_to="payment_proofs/%Y/%m/", blank=True)
    proof_uploaded_at = models.DateTimeField(null=True, blank=True)
    note = models.CharField(max_length=500, blank=True)
    raw = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    verified_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                    related_name="+")

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.get_method_display()} {self.amount} for order {self.order_id} ({self.status})"

    @property
    def is_expired(self):
        return bool(self.expires_at and timezone.now() >= self.expires_at)

    @property
    def can_retry(self):
        """Online payment the customer can still complete."""
        return (self.method == "online" and self.status in ("pending", "failed", "cancelled")
                and not self.is_expired and self.order.status not in ("cancelled", "returned"))

    def set_expiry(self, minutes):
        self.expires_at = timezone.now() + timedelta(minutes=minutes)


class PaymentEvent(models.Model):
    """Audit trail of everything that happened to a payment (and raw webhooks)."""
    payment = models.ForeignKey(Payment, on_delete=models.CASCADE, null=True, blank=True, related_name="events")
    gateway_code = models.CharField(max_length=40, blank=True)
    kind = models.CharField(max_length=40)
    verified = models.BooleanField(default=False)
    data = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                   related_name="+")

    class Meta:
        ordering = ["-created_at"]


# ---------------------------------------------------------------------------
# Wallet withdrawals: how money is sent to customers, fees, and the payout log
# ---------------------------------------------------------------------------
class PayoutMethod(models.Model):
    """One row per withdrawal method customers can pick (JazzCash, Easypaisa, bank...)."""
    MODE_CHOICES = [("manual", "Manual - staff sends the money, then enters the reference"),
                    ("api", "Automatic - sent through the payout API on approval")]
    PROVIDER_CHOICES = [("", "-"), ("test", "Test payout (sandbox simulator)"),
                        ("stripe", "Stripe Connect transfer"), ("http", "Generic payout API (signed JSON)")]

    code = models.SlugField(unique=True, help_text="Matches the withdrawal method: jazzcash, easypaisa, bank, stripe")
    name = models.CharField(max_length=80)
    is_enabled = models.BooleanField(default=True, help_text="Customers can choose this method")
    fee_fixed = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"),
                                    help_text="Fixed charge per withdrawal, Rs")
    fee_percent = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0.00"),
                                      help_text="Percentage of the amount, e.g. 1.5")
    fee_min = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"),
                                  help_text="Smallest total charge, Rs (0 = none)")
    fee_max = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True,
                                  help_text="Largest total charge, Rs (empty = no limit)")
    min_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("500.00"))
    max_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True,
                                     help_text="Empty = no limit")
    processing_time = models.CharField(max_length=60, default="within 2 working days")

    mode = models.CharField(max_length=10, choices=MODE_CHOICES, default="manual")
    provider = models.CharField(max_length=20, choices=PROVIDER_CHOICES, blank=True)
    environment = models.CharField(max_length=10, choices=Environment.choices, default=Environment.SANDBOX)
    api_url = models.URLField(blank=True, help_text="Generic payout API endpoint (provider 'http')")
    api_key = EncryptedTextField(blank=True, help_text="API key / Stripe secret key")
    api_secret = EncryptedTextField(blank=True, help_text="Signing secret (provider 'http')")
    sort_order = models.PositiveSmallIntegerField(default=10)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["sort_order", "name"]

    def __str__(self):
        return self.name

    def fee_for(self, amount):
        amount = Decimal(amount or 0)
        fee = self.fee_fixed + (amount * self.fee_percent / Decimal("100"))
        fee = max(fee, self.fee_min or Decimal("0"))
        if self.fee_max is not None:
            fee = min(fee, self.fee_max)
        fee = min(fee.quantize(Decimal("0.01")), amount)
        return fee

    def fee_text(self):
        parts = []
        if self.fee_percent:
            parts.append(f"{self.fee_percent.normalize():f}%")
        if self.fee_fixed:
            parts.append(f"Rs {self.fee_fixed:,.0f}")
        text = " + ".join(parts) or "Free"
        if self.fee_min and parts:
            text += f" (min Rs {self.fee_min:,.0f})"
        if self.fee_max is not None and parts:
            text += f" (max Rs {self.fee_max:,.0f})"
        return text

    @property
    def automatic(self):
        return self.mode == "api" and bool(self.provider)


class PayoutEvent(models.Model):
    """Audit trail for every withdrawal: requested, sent to the API, paid, failed, rejected."""
    withdrawal = models.ForeignKey("Web.WithdrawalRequest", on_delete=models.CASCADE, related_name="events")
    kind = models.CharField(max_length=40)
    provider = models.CharField(max_length=20, blank=True)
    ok = models.BooleanField(default=False)
    amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    reference = models.CharField(max_length=120, blank=True)
    message = models.CharField(max_length=500, blank=True)
    data = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                   related_name="+")

    class Meta:
        ordering = ["-created_at"]
