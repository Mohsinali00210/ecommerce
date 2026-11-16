from datetime import timedelta

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
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} ({self.get_environment_display()})"

    @property
    def base_url(self):
        return (self.live_base_url if self.environment == Environment.LIVE else self.sandbox_base_url).rstrip("/")

    @property
    def configured(self):
        return bool(self.api_key and self.secret_key and self.base_url)

    def adapter(self):
        from .gateways import get_adapter
        return get_adapter(self.code)(self)

    @classmethod
    def online(cls):
        """The active, configured gateway customers can pay with (or None)."""
        g = cls.objects.filter(is_active=True).first()
        return g if g and g.configured else None


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
    proof = models.FileField(storage=private_storage, upload_to="payment_proofs/%Y/%m/", blank=True)
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
