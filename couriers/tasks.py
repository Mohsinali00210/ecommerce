"""Celery tasks. Scheduled ones are configured in settings.CELERY_BEAT_SCHEDULE."""
import logging
from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.db.models import Q
from django.utils import timezone

log = logging.getLogger("couriers")


@shared_task(bind=True, max_retries=3, default_retry_delay=120)
def auto_book_order(self, order_id):
    from Web.models import Order
    from .adapters.base import CourierError
    from .models import Shipment
    from .services import book_order_with_defaults

    order = Order.objects.filter(pk=order_id).first()
    if not order or Shipment.active_for(order):
        return "skipped"
    try:
        s = book_order_with_defaults(order, auto=True)
        return f"booked {s.tracking_number}"
    except CourierError as exc:
        msg = str(exc)
        # Retry only for network trouble; data problems need a human (shown on the dashboard).
        if "Could not reach" in msg or "HTTP 5" in msg:
            raise self.retry(exc=exc)
        log.warning("Auto-book failed for order %s: %s", order_id, msg)
        return f"failed: {msg}"


@shared_task
def poll_active_shipments():
    """Track every shipment that isn't finished. Runs every COURIER_POLL_MINUTES."""
    from .models import FINAL_STATUSES, Shipment
    from .services import refresh_shipments

    minutes = getattr(settings, "COURIER_POLL_MINUTES", 30)
    cutoff = timezone.now() - timedelta(minutes=max(minutes - 2, 1))
    max_age = timezone.now() - timedelta(days=getattr(settings, "COURIER_TRACK_MAX_DAYS", 45))
    qs = (Shipment.objects.exclude(status__in=FINAL_STATUSES).exclude(tracking_number="")
          .filter(created_at__gte=max_age)
          .filter(Q(last_tracked_at__isnull=True) | Q(last_tracked_at__lt=cutoff))
          .select_related("provider", "credential", "order")[:2000])
    return refresh_shipments(list(qs))


@shared_task
def track_shipment(shipment_id):
    from .models import Shipment
    from .services import refresh_shipments
    s = Shipment.objects.select_related("provider", "credential", "order").get(pk=shipment_id)
    return refresh_shipments([s])


@shared_task
def process_webhook(log_id):
    from .models import WebhookLog
    from .services import process_webhook_updates
    import json

    wl = WebhookLog.objects.select_related("provider").get(pk=log_id)
    if wl.processed:
        return "already processed"
    try:
        try:
            data = json.loads(wl.body) if wl.body else {}
        except ValueError:
            from urllib.parse import parse_qs
            data = {k: v[0] for k, v in parse_qs(wl.body).items()}
        adapter = wl.provider.get_adapter()
        updates = adapter.parse_webhook(data, wl.headers)
        wl.updates_applied = process_webhook_updates(wl.provider, updates)
        wl.success = True
        if not updates:
            wl.error = "No tracking updates found in body."
    except Exception as exc:  # keep the log, surface the error in admin
        wl.error = f"{type(exc).__name__}: {exc}"
        log.exception("Webhook %s failed", log_id)
    wl.processed = True
    wl.save(update_fields=["processed", "success", "updates_applied", "error"])
    return wl.updates_applied


@shared_task
def sync_all_cities():
    from .models import CourierProvider
    from .services import sync_cities
    out = {}
    for p in CourierProvider.objects.filter(is_active=True):
        adapter = p.get_adapter()
        if not adapter.supports_cities or not adapter.credential:
            continue
        try:
            out[p.code] = sync_cities(p)
        except Exception as exc:
            out[p.code] = f"error: {exc}"
    return out


@shared_task(bind=True, max_retries=3, default_retry_delay=300)
def send_shipment_email(self, order_id, title, message, shipment_id=None):
    from Web.models import Order
    from accounts.utils import send_templated_email
    from .models import Shipment

    order = Order.objects.select_related("user").filter(pk=order_id).first()
    if not order or not order.user or not order.user.email:
        return "no email"
    shipment = Shipment.objects.filter(pk=shipment_id).first() if shipment_id else None
    try:
        send_templated_email(
            to_email=order.user.email,
            subject=f"{title} - Order #{order.order_number}",
            template_name="couriers/email_status.html",
            context={"order": order, "title": title, "message": message, "shipment": shipment,
                     "site_url": getattr(settings, "SITE_URL", "")},
        )
    except Exception as exc:
        raise self.retry(exc=exc)
    return "sent"
