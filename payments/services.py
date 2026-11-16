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
    "online": ("Card / JazzCash / Easypaisa", "Pay securely online via Safepay", "bi-credit-card-2-front"),
}


class PaymentNotAllowed(Exception):
    pass


def available_methods(total=None):
    """Payment methods customers can choose right now (respects every admin switch)."""
    s = StoreSettings.get()
    out = []
    if s.cod_enabled:
        ok = total is None or s.cod_allowed_for(total)
        out.append({"code": "cod", "available": ok,
                    "reason": "" if ok else f"Not available above Rs {s.cod_max_amount:,.0f}"})
    if s.bank_transfer_enabled:
        out.append({"code": "bank", "available": True, "reason": "", "details": s.bank_transfer_details})
    if s.online_payments_enabled and PaymentGateway.online():
        out.append({"code": "online", "available": True, "reason": ""})
    for m in out:
        m["label"], m["description"], m["icon"] = METHOD_INFO[m["code"]]
    return out


def validate_method(method, total):
    allowed = {m["code"]: m for m in available_methods(total)}
    m = allowed.get(method)
    if not m:
        if method == "online":
            raise PaymentNotAllowed("Online payment is currently unavailable. Please choose another method.")
        raise PaymentNotAllowed("This payment method is not available.")
    if not m["available"]:
        raise PaymentNotAllowed(m["reason"])


def create_for_order(order, method):
    """Called inside the checkout transaction."""
    gateway = PaymentGateway.online() if method == "online" else None
    p = Payment(order=order, method=method, amount=order.total_amount, gateway=gateway)
    if method == "online":
        p.set_expiry(StoreSettings.get().online_payment_timeout_minutes)
    p.save()
    PaymentEvent.objects.create(payment=p, kind="created", data={"method": method})
    return p


def latest(order):
    return Payment.objects.filter(order=order).select_related("gateway").order_by("-created_at").first()


def start_online(payment, request):
    """Create a gateway session and return the URL to send the customer to."""
    if not StoreSettings.get().online_payments_enabled:
        raise PaymentNotAllowed("Online payment is currently unavailable.")
    gateway = payment.gateway or PaymentGateway.online()
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
                                data={"tracker": session.tracker})
    return session.redirect_url


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
