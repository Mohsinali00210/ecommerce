"""Payment business rules - the checkout, gateway callbacks and admin all use these."""
import logging

from django.db import transaction
from django.urls import reverse
from django.utils import timezone

from adminpanel.models import StoreSettings

from .gateways.base import GatewayError
from .models import Payment, PaymentEvent, PaymentGateway

log = logging.getLogger("app")

METHOD_INFO = {
    "cod": ("Cash on delivery", "Pay when your order arrives", "bi-cash-stack"),
    "bank": ("Bank transfer", "Transfer to our account, then upload the receipt", "bi-bank"),
    "online": ("Card / JazzCash / Easypaisa", "Pay securely online", "bi-credit-card-2-front"),
}


class PaymentNotAllowed(Exception):
    pass


def split_method(value):
    """'online:jazzcash' -> ('online', 'jazzcash'); 'cod' -> ('cod', '')."""
    method, _, gateway = (value or "cod").partition(":")
    return method.strip().lower(), gateway.strip().lower()


def available_methods(total=None, user=None):
    """Payment methods customers can choose right now (respects every admin switch).
    Cash on delivery comes first and is the default. Every active online gateway is its own
    option, with value "online:<gateway code>"."""
    s = StoreSettings.get()
    out = []
    if s.cod_enabled:
        ok = total is None or s.cod_allowed_for(total)
        out.append({"code": "cod", "value": "cod", "available": ok,
                    "reason": "" if ok else f"Not available above Rs {s.cod_max_amount:,.0f}"})
    if s.bank_transfer_enabled:
        out.append({"code": "bank", "value": "bank", "available": True, "reason": "",
                    "details": s.bank_transfer_details})
    for m in out:
        m["label"], m["description"], m["icon"] = METHOD_INFO[m["code"]]
    if s.online_payments_enabled:
        for g in PaymentGateway.online_gateways(user=user):
            cls = g.adapter_class()
            out.append({"code": "online", "value": f"online:{g.code}", "gateway": g.code, "available": True,
                        "reason": "", "label": g.label(), "description": cls.checkout_description,
                        "icon": cls.checkout_icon, "sandbox": g.environment == "sandbox"})
    return out


def validate_method(method, total, gateway_code="", user=None):
    """Raises PaymentNotAllowed; returns the PaymentGateway for online payments (else None)."""
    methods = available_methods(total, user=user)
    if method == "online":
        options = [m for m in methods if m["code"] == "online"]
        m = next((o for o in options if o["gateway"] == gateway_code), None) if gateway_code else             (options[0] if options else None)
        if not m:
            raise PaymentNotAllowed("Online payment is currently unavailable. Please choose another method.")
        return PaymentGateway.objects.get(code=m["gateway"])
    m = next((o for o in methods if o["code"] == method), None)
    if not m:
        raise PaymentNotAllowed("This payment method is not available.")
    if not m["available"]:
        raise PaymentNotAllowed(m["reason"])
    return None


def create_for_order(order, method, gateway=None):
    """Called inside the checkout transaction. `gateway`: PaymentGateway or its code."""
    if method == "online":
        if isinstance(gateway, str) or gateway is None:
            gateway = PaymentGateway.online(code=gateway or None, user=getattr(order, "user", None))
    else:
        gateway = None
    p = Payment(order=order, method=method, amount=order.total_amount, gateway=gateway)
    if method == "online":
        p.set_expiry(StoreSettings.get().online_payment_timeout_minutes)
    p.save()
    PaymentEvent.objects.create(payment=p, gateway_code=gateway.code if gateway else "", kind="created",
                                data={"method": method, "amount": str(p.amount)})
    return p


def latest(order):
    return Payment.objects.filter(order=order).select_related("gateway").order_by("-created_at").first()


def start_online(payment, request):
    """Create a gateway session and return the URL to send the customer to."""
    if not StoreSettings.get().online_payments_enabled:
        raise PaymentNotAllowed("Online payment is currently unavailable.")
    gateway = payment.gateway or PaymentGateway.online(user=getattr(payment.order, "user", None))
    if not gateway or not gateway.configured or not gateway.is_active:
        raise PaymentNotAllowed("Online payment is currently unavailable.")
    if not payment.can_retry:
        raise PaymentNotAllowed("This payment can no longer be completed.")
    return_url = request.build_absolute_uri(reverse("payments:return", args=[payment.pk]))
    cancel_url = request.build_absolute_uri(reverse("payments:cancel", args=[payment.pk]))
    try:
        session = gateway.adapter().start(payment, return_url, cancel_url)
    except GatewayError as exc:
        PaymentEvent.objects.create(payment=payment, gateway_code=gateway.code, kind="start_failed",
                                    data={"error": str(exc), "response": exc.data})
        raise PaymentNotAllowed("We couldn't start the online payment. Please try again in a moment.")
    payment.gateway, payment.tracker, payment.status = gateway, session.tracker, "pending"
    payment.save(update_fields=["gateway", "tracker", "status", "updated_at"])
    PaymentEvent.objects.create(payment=payment, gateway_code=gateway.code, kind="session_started",
                                data={"tracker": session.tracker, "url": session.redirect_url,
                                      "form_post": bool(session.post_fields)})
    return session


def mark_paid(payment, reference="", source="gateway", user=None, data=None):
    """Idempotent: a webhook and the browser return can both arrive."""
    from Web.order_emails import queue_payment_confirmed
    with transaction.atomic():
        p = Payment.objects.select_for_update().select_related("order").get(pk=payment.pk)
        if p.status == "paid":
            return p, False
        p.status, p.paid_at = "paid", timezone.now()
        if reference:
            p.reference = reference[:120]
        if user is not None:
            p.verified_by = user
        p.save()
        order = p.order
        order.payment_status = "paid"
        if reference:
            order.transaction_id = reference[:100]
        if order.status == "cancelled":
            # Paid after the order expired: flag it for a human instead of reviving silently.
            order.notes = ((order.notes or "") + "\nPAYMENT RECEIVED AFTER CANCELLATION - review / refund.").strip()
        order.save()
        PaymentEvent.objects.create(payment=p, gateway_code=p.gateway.code if p.gateway else "", kind="paid",
                                    verified=True, created_by=user,
                                    data={"source": source, "reference": reference, **(data or {})})
        if p.method == "online":
            queue_payment_confirmed(order)
    return p, True


def mark_failed(payment, status="failed", reason="", data=None):
    with transaction.atomic():
        p = Payment.objects.select_for_update().get(pk=payment.pk)
        if p.status in ("paid", "refunded"):
            return p
        p.status = status
        p.note = reason[:500]
        p.save(update_fields=["status", "note", "updated_at"])
        PaymentEvent.objects.create(payment=p, gateway_code=p.gateway.code if p.gateway else "", kind=status,
                                    data={"reason": reason, **(data or {})})
    return p


def expire_unpaid():
    """Cancel online orders that were never paid and release their stock."""
    now = timezone.now()
    count = 0
    for p in Payment.objects.filter(method="online", status__in=["pending", "failed", "cancelled"],
                                    expires_at__lt=now).select_related("order"):
        with transaction.atomic():
            p = Payment.objects.select_for_update().select_related("order").get(pk=p.pk)
            if p.status == "paid" or Payment.objects.filter(order=p.order, status="paid").exists():
                continue
            p.status = "expired"
            p.save(update_fields=["status", "updated_at"])
            order = p.order
            if order.status in ("pending", "submited"):
                order.status = "cancelled"            # Order.save() puts the stock back
                order.payment_status = "cancelled"
                order._skip_status_email = True
                order.notes = ((order.notes or "") + "\nCancelled automatically: online payment not completed.").strip()
                order.save()
            PaymentEvent.objects.create(payment=p, kind="expired")
            count += 1
    return count
