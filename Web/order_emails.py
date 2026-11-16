"""
Customer & admin order emails, sent in the background (Celery) after the
database transaction commits.

Each email carries a signed, expiring link to the order (no sign-in needed),
see order_link() / Web.views_public.order_public.
"""
import logging

from celery import shared_task
from django.conf import settings
from django.core import signing
from django.db import transaction
from django.urls import reverse

log = logging.getLogger("app")

LINK_SALT = "shanzee.order-link.v1"
LINK_MAX_AGE = 180 * 24 * 3600  # 180 days


# ---------------------------------------------------------------------------
# Signed links
# ---------------------------------------------------------------------------
def order_token(order):
    # The order number is part of the signed value so a token can't be reused for another order.
    return signing.dumps({"o": order.pk, "n": order.order_number}, salt=LINK_SALT, compress=True)


def order_from_token(token):
    from Web.models import Order
    try:
        data = signing.loads(token, salt=LINK_SALT, max_age=LINK_MAX_AGE)
    except signing.SignatureExpired:
        return None, "expired"
    except signing.BadSignature:
        return None, "invalid"
    order = Order.objects.filter(pk=data.get("o"), order_number=data.get("n")).first()
    return order, None if order else "invalid"


def order_link(order):
    return settings.SITE_URL + reverse("order_public", args=[order_token(order)])


# ---------------------------------------------------------------------------
# Status copy
# ---------------------------------------------------------------------------
STATUS_COPY = {
    "processing": ("We're preparing your order", "Good news - we've confirmed your order and are getting it ready."),
    "booked": ("Your order is packed", "Your order is packed and handed to our courier partner."),
    "dispatch": ("Your order has been dispatched", "Your order has left our warehouse."),
    "shipped": ("Your order is on its way", "Your parcel is travelling to you."),
    "out_for_delivery": ("Out for delivery today", "Your parcel is out for delivery. Please keep your phone nearby."),
    "delivered": ("Delivered - enjoy!", "Your order has been delivered. Thank you for shopping with Shan Zee."),
    "cancelled": ("Your order was cancelled", "Your order has been cancelled. If you paid online, the refund is on its way."),
    "return_in_transit": ("Your order is being returned", "Your parcel is on its way back to us."),
    "returned": ("Return received", "We've received the returned parcel."),
    "ordersuccessfull": ("Order completed", "Your order is complete. Thank you!"),
}


def _shipment(order):
    try:
        from couriers.models import Shipment
        return Shipment.active_for(order)
    except Exception:
        return None


def _send(to, subject, template, context):
    from accounts.utils import send_templated_email
    send_templated_email(to_email=to, subject=subject, template_name=template, context=context)


# ---------------------------------------------------------------------------
# Tasks
# ---------------------------------------------------------------------------
@shared_task(bind=True, max_retries=3, default_retry_delay=300)
def send_order_confirmation(self, order_id):
    from adminpanel.models import StoreSettings
    from Web.models import Order
    order = Order.objects.select_related("user", "shipping_address").filter(pk=order_id).first()
    if not order or not order.user or not order.user.email:
        return "skipped"
    if not StoreSettings.get().email_order_confirmation:
        return "disabled"
    items = order.items.select_related("product", "variant").prefetch_related("product__images")
    try:
        _send(order.user.email, f"Order #{order.order_number} confirmed - Shan Zee",
              "Web/emails/order_confirmation.html",
              {"order": order, "order_items": items, "order_url": order_link(order),
               "site_url": settings.SITE_URL})
    except Exception as exc:
        raise self.retry(exc=exc)
    return "sent"


@shared_task(bind=True, max_retries=3, default_retry_delay=300)
def send_admin_new_order(self, order_id):
    from adminpanel.models import StoreSettings
    from Web.models import Order
    order = Order.objects.select_related("user", "shipping_address").filter(pk=order_id).first()
    if not order or not StoreSettings.get().email_admin_new_order:
        return "skipped"
    items = order.items.select_related("product", "variant")
    try:
        _send(settings.ADMIN_EMAIL, f"New order #{order.order_number} - Rs {order.total_amount:,.0f}",
              "Web/emails/admin_new_order.html",
              {"order": order, "order_items": items,
               "admin_order_url": settings.SITE_URL + reverse("Orders")})
    except Exception as exc:
        raise self.retry(exc=exc)
    return "sent"


@shared_task(bind=True, max_retries=3, default_retry_delay=300)
def send_order_status_email(self, order_id, status):
    from adminpanel.models import StoreSettings
    from Web.models import Order
    order = Order.objects.select_related("user").filter(pk=order_id).first()
    if not order or not order.user or not order.user.email:
        return "skipped"
    if order.status != status:
        return "stale"  # changed again before we got here; the newer email covers it
    if not StoreSettings.get().emails_status(status):
        return "disabled"
    title, message = STATUS_COPY.get(status, (f"Order update: {order.get_status_display()}",
                                              f"Your order is now: {order.get_status_display()}."))
    shipment = _shipment(order)
    try:
        _send(order.user.email, f"{title} - Order #{order.order_number}", "Web/emails/order_status.html",
              {"order": order, "title": title, "message": message, "status": status,
               "status_label": order.get_status_display(), "shipment": shipment,
               "order_url": order_link(order), "site_url": settings.SITE_URL,
               "steps": _steps(status)})
    except Exception as exc:
        raise self.retry(exc=exc)
    return "sent"


def _steps(status):
    flow = [("processing", "Confirmed"), ("booked", "Packed"), ("shipped", "On the way"),
            ("out_for_delivery", "Out for delivery"), ("delivered", "Delivered")]
    order_index = {"pending": -1, "submited": -1, "processing": 0, "ordersuccessfull": 4, "booked": 1,
                   "dispatch": 2, "shipped": 2, "out_for_delivery": 3, "delivered": 4}
    if status not in order_index:
        return []
    cur = order_index[status]
    return [{"label": label, "done": i <= cur, "current": i == cur} for i, (_, label) in enumerate(flow)]


# ---------------------------------------------------------------------------
# Hooks used by the order flow
# ---------------------------------------------------------------------------
def queue_order_placed(order):
    """Call inside the checkout transaction. Online orders wait for payment."""
    oid = order.pk
    online = (order.payment_method or "").lower() == "online"

    def _go():
        if not online:
            send_order_confirmation.delay(oid)
        send_admin_new_order.delay(oid)
    transaction.on_commit(_go)


def queue_payment_confirmed(order):
    oid = order.pk
    transaction.on_commit(lambda: send_order_confirmation.delay(oid))
