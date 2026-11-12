"""
Courier business logic. Views, Celery tasks and signals all call these
functions, so behaviour is the same whether an action is manual or automatic.
"""
import hashlib
import logging
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

from django.db import IntegrityError, transaction
from django.utils import timezone

from .adapters.base import BookingRequest, CourierError, NotSupported, Party
from .models import (FINAL_STATUSES, CourierCity, CourierProvider, Shipment, ShipmentEvent,
                     ShipmentStatus, ShipperProfile, StatusMapping)

log = logging.getLogger("couriers")

TRACK_BATCH_SIZE = 25


# ---------------------------------------------------------------------------
# Booking
# ---------------------------------------------------------------------------
@dataclass
class BookingInput:
    provider: CourierProvider
    weight_grams: int
    pieces: int
    description: str
    cod_amount: Decimal
    consignee_name: str
    consignee_phone: str
    consignee_address: str
    consignee_email: str = ""
    destination_city: Optional[CourierCity] = None
    destination_city_name: str = ""
    special_instructions: str = ""
    shipment_type: str = ""
    shipper: Optional[ShipperProfile] = None
    tracking_number: str = ""  # manual couriers only


def is_cod(order):
    return (order.payment_method or "").lower() == "cod"


def order_description(order, limit=250):
    parts = []
    for item in order.items.select_related("product", "variant"):
        name = item.product.name if item.product else "Item"
        if item.variant and item.variant.name and item.variant.name.lower() != "default":
            name = f"{name} ({item.variant.name})"
        parts.append(f"{item.quantity}x {name}")
    text = ", ".join(parts) or f"Order {order.order_number}"
    return text if len(text) <= limit else text[: limit - 1] + "…"


def order_weight_grams(order, provider):
    total = Decimal("0")
    for item in order.items.select_related("product"):
        w = getattr(item.product, "weight", None) or 0
        total += Decimal(w) * 1000 * item.quantity  # product.weight is in kg
    grams = int(total)
    return grams if grams > 0 else provider.default_weight_grams


def booking_defaults(order, provider):
    """Pre-filled values for the booking form / auto-booking."""
    addr = order.shipping_address
    user = order.user
    city_name = addr.city if addr else ""
    address_text = ""
    if addr:
        address_text = ", ".join(p for p in [addr.street_address, addr.city, addr.state,
                                             addr.postal_code] if p)
    return {
        "provider": provider,
        "weight_grams": order_weight_grams(order, provider),
        "pieces": 1,
        "description": order_description(order),
        "cod_amount": order.total_amount if is_cod(order) else Decimal("0"),
        "consignee_name": (addr.full_name if addr else "") or (user.get_full_name() if user else ""),
        "consignee_phone": (addr.phone if addr else "") or (getattr(user, "mobile", "") or ""),
        "consignee_email": (getattr(user, "email", "") or "") if user else "",
        "consignee_address": address_text,
        "destination_city": CourierCity.resolve(provider, city_name) if city_name else None,
        "destination_city_name": city_name,
        "special_instructions": (order.notes or "")[:250],
        "shipment_type": provider.default_shipment_type,
        "shipper": ShipperProfile.default(),
    }


def _party_city_id(provider, city_name, origin):
    if not city_name:
        return None
    city = CourierCity.resolve(provider, city_name, destination=not origin)
    return city.external_id if city else None


def book_order(order, data: BookingInput, user=None, auto=False):
    """Book one order. Returns the Shipment. Raises CourierError on failure
    (a 'booking_failed' shipment is kept for the audit trail)."""
    from Web.models import Order

    provider = data.provider
    if not provider.is_active:
        raise CourierError(f"{provider.name} is disabled.")
    shipper = data.shipper or ShipperProfile.default()
    if not shipper:
        raise CourierError("Add your pickup/return details in Couriers > Settings first.")

    adapter = provider.get_adapter()
    credential = adapter.credential

    with transaction.atomic():
        # Lock the order so two clicks / auto + manual can't double book.
        order = Order.objects.select_for_update().get(pk=order.pk)
        existing = Shipment.active_for(order)
        if existing:
            raise CourierError(f"Order already booked with {existing.provider.name} "
                               f"({existing.tracking_number}). Cancel it first to re-book.")

        ret = shipper.returns()
        req = BookingRequest(
            reference=order.order_number,
            shipper=Party(name=shipper.contact_name, phone=shipper.phone, address=shipper.address,
                          city_name=shipper.city, email=shipper.email,
                          city_id=_party_city_id(provider, shipper.city, origin=True)),
            returns=Party(name=ret["name"], phone=ret["phone"], address=ret["address"],
                          city_name=ret["city"],
                          city_id=_party_city_id(provider, ret["city"], origin=False)),
            consignee=Party(name=data.consignee_name, phone=data.consignee_phone,
                            address=data.consignee_address, email=data.consignee_email,
                            city_name=(data.destination_city.name if data.destination_city
                                       else data.destination_city_name),
                            city_id=(data.destination_city.external_id if data.destination_city
                                     else None)),
            weight_grams=int(data.weight_grams),
            pieces=int(data.pieces or 1),
            description=data.description,
            cod_amount=Decimal(data.cod_amount or 0),
            special_instructions=data.special_instructions,
            shipment_type=data.shipment_type,
            tracking_number=data.tracking_number,
        )

        shipment = Shipment(
            order=order, provider=provider, credential=credential, shipper=shipper,
            weight_grams=req.weight_grams, pieces=req.pieces, description=req.description[:500],
            cod_amount=req.cod_amount, special_instructions=req.special_instructions[:500],
            shipment_type=req.shipment_type or "",
            consignee_name=req.consignee.name, consignee_phone=req.consignee.phone,
            consignee_email=req.consignee.email or "", consignee_address=req.consignee.address,
            destination_city=data.destination_city, destination_city_name=req.consignee.city_name or "",
            auto_booked=auto, created_by=user,
        )

        try:
            result = adapter.book(req)
        except CourierError as exc:
            shipment.status = ShipmentStatus.BOOKING_FAILED
            shipment.error_message = str(exc)
            shipment.response_payload = exc.response if isinstance(exc.response, dict) else {}
            # save outside the failing path but inside our transaction
            shipment.save()
            _add_event(shipment, ShipmentStatus.BOOKING_FAILED, "Booking failed", str(exc),
                       source="booking")
            transaction.on_commit(lambda: log.warning("Booking failed for %s: %s",
                                                      order.order_number, exc))
            # Commit the failed attempt, then tell the caller.
            failed = exc
        else:
            failed = None
            shipment.tracking_number = result.tracking_number
            shipment.slip_url = result.slip_url[:500]
            shipment.request_payload = result.request
            shipment.response_payload = result.raw
            shipment.status = ShipmentStatus.BOOKED
            shipment.raw_status = "Booked"
            shipment.booked_at = timezone.now()
            shipment.save()
            _add_event(shipment, ShipmentStatus.BOOKED, "Booked",
                       f"Booked with {provider.name}. CN {result.tracking_number}", source="booking")

            order.tracking_number = result.tracking_number
            fields = ["tracking_number"]
            rule = StatusMapping.lookup(provider, "booked")
            target = rule.order_status if rule else "booked"
            if target and order.status not in ("delivered", "cancelled", "returned"):
                order.status = target
                fields.append("status")
            try:
                with transaction.atomic():
                    _save_order(order, fields)
            except IntegrityError:
                # tracking_number is unique on Order; keep the shipment, skip the copy
                order.tracking_number = None
                _save_order(order, ["status"] if "status" in fields else [])

    if failed:
        raise failed

    _notify(order, "Your order has been shipped",
            f"Your order #{order.order_number} has been handed to {provider.name}. "
            f"Tracking number: {shipment.tracking_number}.", shipment)
    return shipment


def book_order_with_defaults(order, provider=None, user=None, auto=False):
    provider = provider or CourierProvider.objects.filter(is_default=True, is_active=True).first()
    if not provider:
        raise CourierError("No default courier configured.")
    d = booking_defaults(order, provider)
    if not d["destination_city"] and provider.get_adapter().supports_cities:
        raise CourierError(f"Customer city '{d['destination_city_name']}' could not be matched to a "
                           f"{provider.name} city. Book manually and pick the city, or add an alias.")
    return book_order(order, BookingInput(**d), user=user, auto=auto)


def _save_order(order, fields):
    """Order.save() has side effects (QR, stock restore) - always go through it."""
    if not fields:
        return
    order.save()


# ---------------------------------------------------------------------------
# Cancel
# ---------------------------------------------------------------------------
def cancel_shipment(shipment, user=None, reason=""):
    if shipment.status in FINAL_STATUSES:
        raise CourierError(f"Shipment is already {shipment.get_status_display().lower()}.")
    adapter = shipment.provider.get_adapter(shipment.credential)
    if shipment.tracking_number and adapter.supports_cancel:
        adapter.cancel([shipment.tracking_number])
    with transaction.atomic():
        shipment.status = ShipmentStatus.CANCELLED
        shipment.raw_status = "Cancelled"
        shipment.save(update_fields=["status", "raw_status", "modified_at"])
        _add_event(shipment, ShipmentStatus.CANCELLED, "Cancelled",
                   reason or f"Cancelled by {user or 'system'}", source="manual")
        order = shipment.order
        if order.tracking_number == shipment.tracking_number:
            order.tracking_number = None
            if order.status == "booked":
                order.status = "processing"
            order.save()
    return shipment


# ---------------------------------------------------------------------------
# Status updates (polling + webhooks + manual)
# ---------------------------------------------------------------------------
def _fingerprint(raw_status, event_time, description):
    stamp = event_time.isoformat() if event_time else ""
    return hashlib.sha256(f"{raw_status}|{stamp}|{description}".encode()).hexdigest()


def _add_event(shipment, status, raw_status, description="", location="", event_time=None,
               source="api"):
    fp = _fingerprint(raw_status, event_time, description)
    try:
        with transaction.atomic():
            return ShipmentEvent.objects.create(
                shipment=shipment, status=status or "", raw_status=(raw_status or "")[:200],
                description=description or "", location=(location or "")[:200],
                event_time=event_time or timezone.now(), source=source, fingerprint=fp)
    except IntegrityError:
        return None  # duplicate event


ORDER_STATUS_BLOCKERS = {"cancelled"}  # never overwrite an order cancelled by staff


def apply_tracking_update(shipment, update, source="api"):
    """Record events and move shipment/order status. Returns True if status changed."""
    provider = shipment.provider
    for ev in update.events:
        rule = StatusMapping.lookup(provider, ev.raw_status)
        _add_event(shipment, rule.shipment_status if rule else "", ev.raw_status, ev.description,
                   ev.location, ev.event_time, source=source)

    raw = (update.raw_status or (update.events[-1].raw_status if update.events else "")).strip()
    shipment.last_tracked_at = timezone.now()
    shipment.tracking_failures = 0
    if not raw:
        shipment.save(update_fields=["last_tracked_at", "tracking_failures", "modified_at"])
        return False

    rule = StatusMapping.lookup(provider, raw)
    shipment.raw_status = raw[:200]
    shipment.unmapped_status = rule is None
    fields = ["raw_status", "unmapped_status", "last_tracked_at", "tracking_failures", "modified_at"]

    if not update.events:
        _add_event(shipment, rule.shipment_status if rule else "", raw, source=source)

    if rule is None:
        log.info("Unmapped %s status '%s' on %s", provider.code, raw, shipment.tracking_number)
        shipment.save(update_fields=fields)
        return False

    new = rule.shipment_status
    changed = (new != shipment.status and shipment.status not in FINAL_STATUSES
               and not (new == ShipmentStatus.BOOKED and shipment.status != ShipmentStatus.BOOKED))
    if changed:
        shipment.status = new
        fields.append("status")
        if new == ShipmentStatus.DELIVERED:
            shipment.delivered_at = timezone.now()
            fields.append("delivered_at")
    shipment.save(update_fields=fields)

    if changed:
        _apply_order_status(shipment, rule)
    return changed


CUSTOMER_MESSAGES = {
    ShipmentStatus.PICKED_UP: "Your order #{n} has been picked up by {c}.",
    ShipmentStatus.IN_TRANSIT: "Your order #{n} is on its way.",
    ShipmentStatus.OUT_FOR_DELIVERY: "Your order #{n} is out for delivery today. Please keep "
                                     "{amount} ready." ,
    ShipmentStatus.DELIVERY_FAILED: "{c} could not deliver order #{n}. They will try again - "
                                    "contact us if you need help.",
    ShipmentStatus.DELIVERED: "Your order #{n} has been delivered. Thank you for shopping with us!",
    ShipmentStatus.RETURN_IN_TRANSIT: "Order #{n} is being returned to us.",
    ShipmentStatus.RETURNED: "Order #{n} was returned to us.",
}


def _apply_order_status(shipment, rule):
    order = shipment.order
    target = rule.order_status
    if target and order.status != target and order.status not in ORDER_STATUS_BLOCKERS:
        order.status = target
        if target == "delivered" and not order.delivered_at:
            order.delivered_at = timezone.now()
        order.save()
    if rule.notify_customer and shipment.status in CUSTOMER_MESSAGES:
        amount = (f"Rs {shipment.cod_amount:,.0f}" if shipment.cod_amount else "your ID")
        if shipment.status == ShipmentStatus.OUT_FOR_DELIVERY and not shipment.cod_amount:
            msg = f"Your order #{order.order_number} is out for delivery today."
        else:
            msg = CUSTOMER_MESSAGES[shipment.status].format(
                n=order.order_number, c=shipment.provider.name, amount=amount)
        _notify(order, f"Order {shipment.get_status_display().lower()}", msg, shipment)


def set_status_manually(shipment, shipment_status, user, note=""):
    rule = StatusMapping(shipment_status=shipment_status, notify_customer=True,
                         order_status=_default_order_status(shipment_status))
    _add_event(shipment, shipment_status, dict(ShipmentStatus.choices)[shipment_status],
               note or f"Set by {user}", source="manual")
    if shipment.status != shipment_status:
        shipment.status = shipment_status
        if shipment_status == ShipmentStatus.DELIVERED:
            shipment.delivered_at = timezone.now()
        shipment.save()
        _apply_order_status(shipment, rule)


def _default_order_status(shipment_status):
    return {
        ShipmentStatus.BOOKED: "booked", ShipmentStatus.PICKED_UP: "shipped",
        ShipmentStatus.IN_TRANSIT: "shipped", ShipmentStatus.OUT_FOR_DELIVERY: "out_for_delivery",
        ShipmentStatus.DELIVERED: "delivered", ShipmentStatus.RETURN_IN_TRANSIT: "return_in_transit",
        ShipmentStatus.RETURNED: "returned",
    }.get(shipment_status, "")


def refresh_shipments(shipments):
    """Track a list of shipments through their courier APIs (batched)."""
    groups = {}
    for s in shipments:
        if s.tracking_number and not s.is_final:
            groups.setdefault((s.provider_id, s.credential_id), []).append(s)
    changed = errors = 0
    for (_pid, _cid), items in groups.items():
        adapter = items[0].provider.get_adapter(items[0].credential)
        if not adapter.supports_tracking:
            continue
        for i in range(0, len(items), TRACK_BATCH_SIZE):
            batch = items[i:i + TRACK_BATCH_SIZE]
            try:
                results = adapter.track([s.tracking_number for s in batch])
            except (CourierError, NotSupported) as exc:
                errors += len(batch)
                for s in batch:
                    s.tracking_failures += 1
                    s.error_message = f"Tracking failed: {exc}"[:2000]
                    s.last_tracked_at = timezone.now()
                    s.save(update_fields=["tracking_failures", "error_message", "last_tracked_at"])
                continue
            for s in batch:
                upd = results.get(s.tracking_number)
                if upd and apply_tracking_update(s, upd, source="api"):
                    changed += 1
    return {"changed": changed, "errors": errors}


def process_webhook_updates(provider, updates):
    applied = 0
    for upd in updates:
        qs = Shipment.objects.filter(provider=provider, tracking_number=upd.tracking_number)
        for shipment in qs:
            apply_tracking_update(shipment, upd, source="webhook")
            applied += 1
    return applied


# ---------------------------------------------------------------------------
# Cities
# ---------------------------------------------------------------------------
def sync_cities(provider):
    adapter = provider.get_adapter()
    cities = adapter.get_cities()
    now = timezone.now()
    seen = set()
    with transaction.atomic():
        for c in cities:
            obj, _ = CourierCity.objects.update_or_create(
                provider=provider, external_id=c.external_id,
                defaults={"name": c.name, "allow_origin": c.allow_origin,
                          "allow_destination": c.allow_destination, "is_active": True,
                          "synced_at": now})
            seen.add(obj.pk)
        stale = CourierCity.objects.filter(provider=provider).exclude(pk__in=seen)
        stale.update(is_active=False)
    return len(seen)


# ---------------------------------------------------------------------------
# Customer notifications
# ---------------------------------------------------------------------------
def _notify(order, title, message, shipment=None):
    if not order.user_id:
        return
    from Web.models import Notification, NotificationRecipient

    ntype = "order_status"
    if shipment and shipment.status == ShipmentStatus.DELIVERED:
        ntype = "order_delivered"
    elif shipment and shipment.status == ShipmentStatus.BOOKED:
        ntype = "order_dispatched"
    n = Notification.objects.create(title=title, message=message, notification_type=ntype,
                                    is_general=False, is_active=True, order=order)
    NotificationRecipient.objects.create(notification=n, user_id=order.user_id, is_read=False)

    from .tasks import send_shipment_email
    sid = shipment.pk if shipment else None
    transaction.on_commit(lambda: send_shipment_email.delay(order.pk, title, message, sid))
