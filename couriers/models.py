"""
Courier integration data model.

Adding a courier = add a CourierProvider row (+ CourierCredential).
If the courier has an API shape no adapter covers yet, add one adapter
class in couriers/adapters/ (see adapters/base.py).
"""
import re
import secrets

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone

from .crypto import EncryptedTextField


# ---------------------------------------------------------------------------
# Canonical shipment statuses (every courier's statuses are mapped onto these)
# ---------------------------------------------------------------------------
class ShipmentStatus(models.TextChoices):
    BOOKED = "booked", "Booked"
    PICKED_UP = "picked_up", "Picked up"
    IN_TRANSIT = "in_transit", "In transit"
    OUT_FOR_DELIVERY = "out_for_delivery", "Out for delivery"
    DELIVERY_FAILED = "delivery_failed", "Delivery attempt failed"
    DELIVERED = "delivered", "Delivered"
    RETURN_IN_TRANSIT = "return_in_transit", "Returning to shipper"
    RETURNED = "returned", "Returned to shipper"
    CANCELLED = "cancelled", "Cancelled"
    BOOKING_FAILED = "booking_failed", "Booking failed"


FINAL_STATUSES = {ShipmentStatus.DELIVERED, ShipmentStatus.RETURNED,
                  ShipmentStatus.CANCELLED, ShipmentStatus.BOOKING_FAILED}
# Shipments in these statuses don't block re-booking the order.
INACTIVE_STATUSES = {ShipmentStatus.CANCELLED, ShipmentStatus.BOOKING_FAILED}


class Environment(models.TextChoices):
    SANDBOX = "sandbox", "Sandbox / staging"
    LIVE = "live", "Live / production"


def normalize_city(name):
    return re.sub(r"[^a-z0-9]", "", (name or "").lower())


def _new_token():
    return secrets.token_urlsafe(32)


class TimeStamped(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    modified_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


# ---------------------------------------------------------------------------
# Provider + credentials
# ---------------------------------------------------------------------------
class CourierProvider(TimeStamped):
    name = models.CharField(max_length=100)
    code = models.SlugField(max_length=50, unique=True,
                            help_text="Short id used in URLs, e.g. leopards, tcs, postex")
    adapter = models.CharField(
        max_length=50,
        help_text="Which integration code talks to this courier (see couriers/adapters). "
                  "Use 'manual' for couriers without an API.")
    environment = models.CharField(max_length=10, choices=Environment.choices,
                                   default=Environment.SANDBOX)
    live_base_url = models.URLField(blank=True)
    sandbox_base_url = models.URLField(blank=True)
    tracking_url_template = models.CharField(
        max_length=300, blank=True,
        help_text="Public tracking page, use {tracking_number}. Shown to customers.")

    is_active = models.BooleanField(default=True)
    is_default = models.BooleanField(default=False, help_text="Used for auto-booking.")

    # Automation
    auto_book_enabled = models.BooleanField(
        default=False, help_text="Book automatically when an order reaches the status below.")
    auto_book_on_status = models.CharField(max_length=20, default="processing")
    auto_book_payment_methods = models.CharField(
        max_length=100, default="cod",
        help_text="Comma separated payment methods that may be auto-booked, e.g. cod,card")

    # Booking defaults
    default_weight_grams = models.PositiveIntegerField(default=500)
    default_shipment_type = models.CharField(max_length=30, blank=True,
                                             help_text="Courier service type, e.g. overnight")
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "name"]
        constraints = [
            models.UniqueConstraint(fields=["is_default"], condition=Q(is_default=True),
                                    name="one_default_courier"),
        ]

    def __str__(self):
        return self.name

    @property
    def base_url(self):
        return self.live_base_url if self.environment == Environment.LIVE else self.sandbox_base_url

    def get_credential(self):
        return (self.credentials.filter(is_active=True, environment=self.environment)
                .order_by("-modified_at").first())

    def get_adapter(self, credential=None):
        from .adapters import get_adapter_class
        return get_adapter_class(self.adapter)(self, credential or self.get_credential())

    def tracking_url(self, tracking_number):
        if not self.tracking_url_template or not tracking_number:
            return ""
        return self.tracking_url_template.replace("{tracking_number}", tracking_number)

    def auto_book_methods(self):
        return {m.strip().lower() for m in self.auto_book_payment_methods.split(",") if m.strip()}


class CourierCredential(TimeStamped):
    provider = models.ForeignKey(CourierProvider, on_delete=models.CASCADE, related_name="credentials")
    label = models.CharField(max_length=100, default="Main account")
    environment = models.CharField(max_length=10, choices=Environment.choices,
                                   default=Environment.SANDBOX)
    api_key = EncryptedTextField(blank=True)
    api_password = EncryptedTextField(blank=True)
    account_number = models.CharField(max_length=100, blank=True)
    extra = models.JSONField(default=dict, blank=True,
                             help_text="Non-secret extra settings some couriers need (JSON)")
    extra_secret = EncryptedTextField(blank=True,
                                      help_text="Any other secret a courier needs (stored encrypted)")
    webhook_token = models.CharField(max_length=64, unique=True, default=_new_token,
                                     help_text="Secret part of the webhook URL")
    is_active = models.BooleanField(default=True)
    last_verified_at = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True)

    class Meta:
        ordering = ["provider", "environment", "label"]

    def __str__(self):
        return f"{self.provider} - {self.label} ({self.get_environment_display()})"

    @staticmethod
    def mask(value):
        if not value:
            return ""
        return "•" * 6 + value[-4:] if len(value) > 4 else "•" * 6

    def rotate_webhook_token(self):
        self.webhook_token = _new_token()
        self.save(update_fields=["webhook_token", "modified_at"])


# ---------------------------------------------------------------------------
# Your own pickup / return details
# ---------------------------------------------------------------------------
class ShipperProfile(TimeStamped):
    label = models.CharField(max_length=100, default="Main warehouse")
    contact_name = models.CharField(max_length=150)
    phone = models.CharField(max_length=30)
    email = models.EmailField(blank=True)
    address = models.TextField()
    city = models.CharField(max_length=100)

    # Where returned parcels should go (defaults to the pickup address)
    return_same_as_pickup = models.BooleanField(default=True)
    return_contact_name = models.CharField(max_length=150, blank=True)
    return_phone = models.CharField(max_length=30, blank=True)
    return_address = models.TextField(blank=True)
    return_city = models.CharField(max_length=100, blank=True)

    is_default = models.BooleanField(default=False)

    class Meta:
        ordering = ["-is_default", "label"]
        constraints = [
            models.UniqueConstraint(fields=["is_default"], condition=Q(is_default=True),
                                    name="one_default_shipper"),
        ]

    def __str__(self):
        return f"{self.label} ({self.city})"

    def returns(self):
        """Effective return details."""
        if self.return_same_as_pickup:
            return {"name": self.contact_name, "phone": self.phone,
                    "address": self.address, "city": self.city}
        return {"name": self.return_contact_name or self.contact_name,
                "phone": self.return_phone or self.phone,
                "address": self.return_address or self.address,
                "city": self.return_city or self.city}

    @classmethod
    def default(cls):
        return cls.objects.filter(is_default=True).first() or cls.objects.first()


# ---------------------------------------------------------------------------
# Cities (each courier has its own city ids)
# ---------------------------------------------------------------------------
class CourierCity(models.Model):
    provider = models.ForeignKey(CourierProvider, on_delete=models.CASCADE, related_name="cities")
    external_id = models.CharField(max_length=50)
    name = models.CharField(max_length=150)
    normalized = models.CharField(max_length=150, db_index=True, editable=False)
    aliases = models.CharField(max_length=300, blank=True,
                               help_text="Other spellings, comma separated (e.g. Isb, Islamabad Capital)")
    allow_origin = models.BooleanField(default=True)
    allow_destination = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)
    synced_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "courier cities"
        constraints = [
            models.UniqueConstraint(fields=["provider", "external_id"], name="uniq_courier_city"),
        ]

    def __str__(self):
        return f"{self.name} ({self.provider.code}:{self.external_id})"

    def save(self, *args, **kwargs):
        self.normalized = normalize_city(self.name)
        super().save(*args, **kwargs)

    @classmethod
    def resolve(cls, provider, city_name, destination=True):
        """Find the courier city for a free-text city name, or None."""
        key = normalize_city(city_name)
        if not key:
            return None
        qs = cls.objects.filter(provider=provider, is_active=True)
        qs = qs.filter(allow_destination=True) if destination else qs.filter(allow_origin=True)
        city = qs.filter(normalized=key).first()
        if city:
            return city
        for c in qs.exclude(aliases=""):
            if key in {normalize_city(a) for a in c.aliases.split(",")}:
                return c
        return None


# ---------------------------------------------------------------------------
# Status mapping (courier wording -> our statuses), editable in admin
# ---------------------------------------------------------------------------
class StatusMapping(models.Model):
    MATCH_EXACT = "exact"
    MATCH_CONTAINS = "contains"
    provider = models.ForeignKey(CourierProvider, on_delete=models.CASCADE, null=True, blank=True,
                                 related_name="status_mappings",
                                 help_text="Leave empty to apply to every courier")
    courier_status = models.CharField(max_length=150, help_text="Status text as the courier sends it")
    match_type = models.CharField(max_length=10, default=MATCH_CONTAINS,
                                  choices=[(MATCH_EXACT, "Exact"), (MATCH_CONTAINS, "Contains")])
    shipment_status = models.CharField(max_length=20, choices=ShipmentStatus.choices)
    order_status = models.CharField(max_length=20, blank=True,
                                    help_text="Order status to set (empty = don't change the order)")
    notify_customer = models.BooleanField(default=True)
    priority = models.PositiveIntegerField(default=100, help_text="Lower is checked first")

    class Meta:
        ordering = ["priority", "id"]

    def __str__(self):
        return f"{self.courier_status} -> {self.shipment_status}"

    def matches(self, raw):
        a, b = raw.strip().lower(), self.courier_status.strip().lower()
        return a == b if self.match_type == self.MATCH_EXACT else b in a

    @classmethod
    def lookup(cls, provider, raw_status):
        if not raw_status:
            return None
        rules = cls.objects.filter(Q(provider=provider) | Q(provider__isnull=True))
        # provider-specific rules win over global ones at equal priority
        for rule in sorted(rules, key=lambda r: (r.priority, r.provider_id is None, r.id)):
            if rule.matches(raw_status):
                return rule
        return None


# ---------------------------------------------------------------------------
# Shipments
# ---------------------------------------------------------------------------
class Shipment(TimeStamped):
    order = models.ForeignKey("Web.Order", on_delete=models.CASCADE, related_name="shipments")
    provider = models.ForeignKey(CourierProvider, on_delete=models.PROTECT, related_name="shipments")
    credential = models.ForeignKey(CourierCredential, on_delete=models.SET_NULL, null=True, blank=True)
    shipper = models.ForeignKey(ShipperProfile, on_delete=models.SET_NULL, null=True, blank=True)

    tracking_number = models.CharField(max_length=100, blank=True, db_index=True)
    slip_url = models.URLField(max_length=500, blank=True)
    status = models.CharField(max_length=20, choices=ShipmentStatus.choices,
                              default=ShipmentStatus.BOOKED)
    raw_status = models.CharField(max_length=200, blank=True, help_text="Last status text from courier")
    unmapped_status = models.BooleanField(default=False,
                                          help_text="Courier sent a status with no mapping rule")

    # Packet details
    weight_grams = models.PositiveIntegerField()
    pieces = models.PositiveIntegerField(default=1)
    description = models.CharField(max_length=500)
    cod_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    special_instructions = models.CharField(max_length=500, blank=True)
    shipment_type = models.CharField(max_length=30, blank=True)

    # Consignee snapshot (what we actually sent)
    consignee_name = models.CharField(max_length=255)
    consignee_phone = models.CharField(max_length=30)
    consignee_email = models.EmailField(blank=True)
    consignee_address = models.TextField()
    destination_city = models.ForeignKey(CourierCity, on_delete=models.SET_NULL, null=True, blank=True)
    destination_city_name = models.CharField(max_length=150, blank=True)

    request_payload = models.JSONField(default=dict, blank=True)
    response_payload = models.JSONField(default=dict, blank=True)
    error_message = models.TextField(blank=True)

    booked_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    last_tracked_at = models.DateTimeField(null=True, blank=True)
    tracking_failures = models.PositiveIntegerField(default=0)
    auto_booked = models.BooleanField(default=False)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
                                   null=True, blank=True, related_name="+")

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            # Only one live shipment per order (cancelled/failed ones don't count)
            models.UniqueConstraint(
                fields=["order"],
                condition=~Q(status__in=["cancelled", "booking_failed"]),
                name="one_active_shipment_per_order"),
        ]
        indexes = [models.Index(fields=["status", "last_tracked_at"])]

    def __str__(self):
        return f"{self.provider.code}:{self.tracking_number or 'unbooked'} (order {self.order_id})"

    @property
    def is_final(self):
        return self.status in FINAL_STATUSES

    @property
    def tracking_url(self):
        return self.provider.tracking_url(self.tracking_number)

    @classmethod
    def active_for(cls, order):
        return cls.objects.filter(order=order).exclude(status__in=INACTIVE_STATUSES).first()


class ShipmentEvent(models.Model):
    SOURCE_CHOICES = [("booking", "Booking"), ("api", "Tracking API"), ("webhook", "Webhook"),
                      ("manual", "Manual"), ("system", "System")]
    shipment = models.ForeignKey(Shipment, on_delete=models.CASCADE, related_name="events")
    status = models.CharField(max_length=20, choices=ShipmentStatus.choices, blank=True)
    raw_status = models.CharField(max_length=200, blank=True)
    description = models.TextField(blank=True)
    location = models.CharField(max_length=200, blank=True)
    event_time = models.DateTimeField(default=timezone.now)
    source = models.CharField(max_length=10, choices=SOURCE_CHOICES, default="api")
    fingerprint = models.CharField(max_length=64, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-event_time", "-id"]
        constraints = [
            models.UniqueConstraint(fields=["shipment", "fingerprint"], name="uniq_shipment_event"),
        ]

    def __str__(self):
        return f"{self.shipment_id}: {self.raw_status or self.status} @ {self.event_time:%Y-%m-%d %H:%M}"


class WebhookLog(models.Model):
    provider = models.ForeignKey(CourierProvider, on_delete=models.SET_NULL, null=True, blank=True)
    received_at = models.DateTimeField(auto_now_add=True)
    remote_ip = models.GenericIPAddressField(null=True, blank=True)
    headers = models.JSONField(default=dict, blank=True)
    body = models.TextField(blank=True)
    authenticated = models.BooleanField(default=False)
    processed = models.BooleanField(default=False)
    success = models.BooleanField(default=False)
    updates_applied = models.PositiveIntegerField(default=0)
    error = models.TextField(blank=True)

    class Meta:
        ordering = ["-received_at"]

    def __str__(self):
        return f"Webhook {self.provider_id} @ {self.received_at:%Y-%m-%d %H:%M}"
