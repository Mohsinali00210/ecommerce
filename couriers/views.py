import ipaddress
import json
import logging
import secrets

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import user_passes_test
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, Q
from django.http import Http404, HttpResponseNotAllowed, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from Web.models import Order

from .adapters.base import CourierError, NotSupported
from .forms import (BookingForm, CredentialForm, ManualStatusForm, ProviderForm, ShipperForm,
                    StatusMappingForm)
from .models import (FINAL_STATUSES, INACTIVE_STATUSES, CourierCity, CourierCredential,
                     CourierProvider, Shipment, ShipmentStatus, ShipperProfile, StatusMapping,
                     WebhookLog)
from . import services

log = logging.getLogger("couriers")

staff_required = user_passes_test(lambda u: u.is_authenticated and u.is_active and u.is_staff,
                                  login_url="login")

READY_STATUSES = ("pending", "submited", "processing", "ordersuccessfull")


def _default_provider():
    return (CourierProvider.objects.filter(is_default=True, is_active=True).first()
            or CourierProvider.objects.filter(is_active=True).first())


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------
@staff_required
def dashboard(request):
    qs = Shipment.objects.select_related("order", "provider").order_by("-created_at")
    status = request.GET.get("status", "")
    provider = request.GET.get("provider", "")
    q = request.GET.get("q", "").strip()
    if status == "attention":
        qs = qs.filter(Q(status__in=["booking_failed", "delivery_failed"]) | Q(unmapped_status=True)
                       | Q(tracking_failures__gte=3))
    elif status:
        qs = qs.filter(status=status)
    if provider:
        qs = qs.filter(provider__code=provider)
    if q:
        qs = qs.filter(Q(tracking_number__icontains=q) | Q(order__order_number__icontains=q)
                       | Q(consignee_name__icontains=q) | Q(consignee_phone__icontains=q))
    page = Paginator(qs, 25).get_page(request.GET.get("page"))

    counts = dict(Shipment.objects.values_list("status").annotate(n=Count("id")))
    attention = Shipment.objects.filter(
        Q(status__in=["booking_failed", "delivery_failed"]) | Q(unmapped_status=True)
        | Q(tracking_failures__gte=3)).count()

    booked_orders = Shipment.objects.exclude(status__in=INACTIVE_STATUSES).values("order_id")
    ready = (Order.objects.filter(status__in=READY_STATUSES).exclude(pk__in=booked_orders)
             .select_related("user", "shipping_address").order_by("-created_at")[:100])

    return render(request, "couriers/dashboard.html", {
        "page": page, "counts": counts, "attention": attention, "ready": ready,
        "statuses": ShipmentStatus.choices, "providers": CourierProvider.objects.all(),
        "f_status": status, "f_provider": provider, "q": q,
        "default_provider": _default_provider(),
        "setup_missing": not ShipperProfile.objects.exists() or not _default_provider(),
    })


# ---------------------------------------------------------------------------
# Booking
# ---------------------------------------------------------------------------
@staff_required
def book_order(request, order_id):
    order = get_object_or_404(Order.objects.select_related("user", "shipping_address"), pk=order_id)
    active = Shipment.active_for(order)
    if active:
        messages.info(request, f"Order already booked ({active.tracking_number}).")
        return redirect("couriers:shipment", pk=active.pk)

    provider = None
    if request.GET.get("provider"):
        provider = CourierProvider.objects.filter(pk=request.GET["provider"], is_active=True).first()
    provider = provider or _default_provider()
    if not provider:
        messages.error(request, "Add a courier first (Couriers > Settings).")
        return redirect("couriers:settings")
    if not ShipperProfile.objects.exists():
        messages.error(request, "Add your pickup/return details first (Couriers > Settings).")
        return redirect("couriers:settings")

    if request.method == "POST":
        form = BookingForm(request.POST, provider=provider)
        if form.is_valid():
            data = services.BookingInput(**form.cleaned_data)
            try:
                shipment = services.book_order(order, data, user=request.user)
            except CourierError as exc:
                messages.error(request, f"Booking failed: {exc}")
            else:
                messages.success(request, f"Booked with {shipment.provider.name}. "
                                          f"CN {shipment.tracking_number}")
                return redirect("couriers:shipment", pk=shipment.pk)
    else:
        initial = services.booking_defaults(order, provider)
        form = BookingForm(initial=initial, provider=provider)

    adapter = provider.get_adapter()
    return render(request, "couriers/book.html", {
        "order": order, "form": form, "provider": provider, "adapter": adapter,
        "providers": CourierProvider.objects.filter(is_active=True),
        "failed": Shipment.objects.filter(order=order, status="booking_failed")[:5],
        "city_count": provider.cities.filter(is_active=True).count(),
    })


@staff_required
@require_POST
def bulk_book(request):
    ids = [int(i) for i in request.POST.getlist("order_ids") if i.isdigit()]
    provider = (CourierProvider.objects.filter(pk=request.POST.get("provider"), is_active=True).first()
                or _default_provider())
    if not ids or not provider:
        messages.error(request, "Select orders and a courier.")
        return redirect("couriers:dashboard")
    ok, failed = [], []
    for order in Order.objects.filter(pk__in=ids):
        try:
            s = services.book_order_with_defaults(order, provider=provider, user=request.user)
            ok.append(f"{order.order_number} → {s.tracking_number}")
        except CourierError as exc:
            failed.append(f"{order.order_number}: {exc}")
    if ok:
        messages.success(request, f"Booked {len(ok)} order(s): " + "; ".join(ok))
    if failed:
        messages.error(request, f"{len(failed)} failed (open them to fix): " + " | ".join(failed))
    return redirect("couriers:dashboard")


# ---------------------------------------------------------------------------
# Shipment detail + actions
# ---------------------------------------------------------------------------
@staff_required
def shipment_detail(request, pk):
    s = get_object_or_404(Shipment.objects.select_related("order", "provider", "shipper"), pk=pk)
    adapter = s.provider.get_adapter(s.credential)
    return render(request, "couriers/shipment.html", {
        "s": s, "events": s.events.all()[:200], "adapter": adapter,
        "status_form": ManualStatusForm(initial={"status": s.status}),
        "other_attempts": Shipment.objects.filter(order=s.order).exclude(pk=s.pk),
        "is_final": s.status in FINAL_STATUSES,
    })


@staff_required
@require_POST
def shipment_refresh(request, pk):
    s = get_object_or_404(Shipment, pk=pk)
    res = services.refresh_shipments([s])
    s.refresh_from_db()
    if res["errors"]:
        messages.error(request, s.error_message or "Tracking failed.")
    else:
        messages.success(request, f"Tracking refreshed: {s.raw_status or s.get_status_display()}")
    return redirect("couriers:shipment", pk=pk)


@staff_required
@require_POST
def shipment_cancel(request, pk):
    s = get_object_or_404(Shipment, pk=pk)
    try:
        services.cancel_shipment(s, user=request.user, reason=request.POST.get("reason", ""))
        messages.success(request, "Shipment cancelled. You can book the order again.")
    except CourierError as exc:
        messages.error(request, f"Cancel failed: {exc}")
    return redirect("couriers:shipment", pk=pk)


@staff_required
@require_POST
def shipment_set_status(request, pk):
    s = get_object_or_404(Shipment, pk=pk)
    form = ManualStatusForm(request.POST)
    if form.is_valid():
        services.set_status_manually(s, form.cleaned_data["status"], request.user,
                                     form.cleaned_data["note"])
        messages.success(request, "Status updated.")
    return redirect("couriers:shipment", pk=pk)


@staff_required
def order_shipment_info(request, order_id):
    """JSON for the Orders modal in the admin panel."""
    order = get_object_or_404(Order, pk=order_id)
    s = Shipment.active_for(order)
    return JsonResponse({
        "book_url": reverse("couriers:book", args=[order.pk]),
        "shipment": None if not s else {
            "id": s.pk, "provider": s.provider.name, "tracking_number": s.tracking_number,
            "status": s.get_status_display(), "raw_status": s.raw_status, "slip_url": s.slip_url,
            "url": reverse("couriers:shipment", args=[s.pk]),
        },
    })


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------
@staff_required
def settings_page(request):
    providers = CourierProvider.objects.annotate(
        n_cities=Count("cities", filter=Q(cities__is_active=True), distinct=True)
    ).prefetch_related("credentials")
    rows = []
    for p in providers:
        creds = []
        for c in p.credentials.all():
            creds.append({"obj": c, "key": CourierCredential.mask(c.api_key),
                          "webhook": p.webhook_url(c)})
        rows.append({"p": p, "creds": creds, "adapter": p.get_adapter()})
    return render(request, "couriers/settings.html", {
        "rows": rows, "shippers": ShipperProfile.objects.all(),
        "mappings": StatusMapping.objects.select_related("provider"),
        "logs": WebhookLog.objects.select_related("provider")[:20],
        "unmapped": (Shipment.objects.filter(unmapped_status=True).values("provider__name", "raw_status")
                     .annotate(n=Count("id")).order_by("-n")[:20]),
    })


def _edit(request, form_cls, instance, title, back="couriers:settings", extra=None, initial=None,
          context=None):
    form = form_cls(request.POST or None, instance=instance, initial=initial)
    if request.method == "POST" and form.is_valid():
        obj = form.save(commit=False)
        if extra:
            extra(obj)
        obj.save()
        messages.success(request, f"{title} saved.")
        return redirect(back)
    return render(request, "couriers/edit.html", {"form": form, "title": title, "back": back,
                                                  "instance": instance, **(context or {})})


@staff_required
def provider_edit(request, pk=None):
    obj = get_object_or_404(CourierProvider, pk=pk) if pk else None
    return _edit(request, ProviderForm, obj, "Courier")


@staff_required
def credential_edit(request, provider_id, pk=None):
    provider = get_object_or_404(CourierProvider, pk=provider_id)
    obj = get_object_or_404(CourierCredential, pk=pk, provider=provider) if pk else None

    def attach(c):
        c.provider = provider
    ctx = {"webhook_url": provider.webhook_url(obj) if obj else "",
           "webhook_prefix": provider.public_base() + f"/couriers/webhook/{provider.code}/"}
    return _edit(request, CredentialForm, obj, f"{provider.name} credentials", extra=attach, context=ctx)


@staff_required
def shipper_edit(request, pk=None):
    obj = get_object_or_404(ShipperProfile, pk=pk) if pk else None
    return _edit(request, ShipperForm, obj, "Pickup / return details")


@staff_required
def mapping_edit(request, pk=None):
    obj = get_object_or_404(StatusMapping, pk=pk) if pk else None
    initial = None
    if obj is None and request.GET.get("raw"):
        initial = {"courier_status": request.GET["raw"], "match_type": "exact",
                   "provider": CourierProvider.objects.filter(name=request.GET.get("p")).first()}
    return _edit(request, StatusMappingForm, obj, "Status mapping", initial=initial)


@staff_required
@require_POST
def mapping_delete(request, pk):
    get_object_or_404(StatusMapping, pk=pk).delete()
    messages.success(request, "Mapping deleted.")
    return redirect("couriers:settings")


@staff_required
@require_POST
def provider_test(request, pk):
    p = get_object_or_404(CourierProvider, pk=pk)
    cred = p.get_credential()
    try:
        msg = p.get_adapter().test_connection()
        if cred:
            cred.last_error = ""
            from django.utils import timezone
            cred.last_verified_at = timezone.now()
            cred.save(update_fields=["last_error", "last_verified_at"])
        messages.success(request, f"{p.name}: {msg}")
    except (CourierError, NotSupported) as exc:
        if cred:
            cred.last_error = str(exc)[:2000]
            cred.save(update_fields=["last_error"])
        messages.error(request, f"{p.name}: {exc}")
    return redirect("couriers:settings")


@staff_required
@require_POST
def provider_sync_cities(request, pk):
    p = get_object_or_404(CourierProvider, pk=pk)
    try:
        n = services.sync_cities(p)
        messages.success(request, f"{p.name}: {n} cities synced.")
    except (CourierError, NotSupported) as exc:
        messages.error(request, f"{p.name}: {exc}")
    return redirect("couriers:settings")


@staff_required
@require_POST
def credential_rotate_token(request, pk):
    c = get_object_or_404(CourierCredential, pk=pk)
    c.rotate_webhook_token()
    messages.success(request, "New webhook URL generated. Update it with the courier.")
    return redirect("couriers:settings")


@staff_required
def webhook_log_detail(request, pk):
    wl = get_object_or_404(WebhookLog, pk=pk)
    return render(request, "couriers/webhook_log.html", {"wl": wl})


# ---------------------------------------------------------------------------
# Public endpoints
# ---------------------------------------------------------------------------
@require_GET
def city_list(request):
    """City names of the default courier, for the checkout/address city picker."""
    p = _default_provider()
    if not p:
        return JsonResponse({"cities": []})
    names = (CourierCity.objects.filter(provider=p, is_active=True, allow_destination=True)
             .order_by("name").values_list("name", flat=True).distinct())
    resp = JsonResponse({"courier": p.name, "cities": list(names)})
    resp["Cache-Control"] = "public, max-age=3600"
    return resp


def _client_ip(request):
    if getattr(settings, "COURIER_TRUST_X_FORWARDED_FOR", False):
        fwd = request.META.get("HTTP_X_FORWARDED_FOR", "")
        if fwd:
            return fwd.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


@csrf_exempt  # couriers can't send our CSRF token; the URL token authenticates instead
def webhook(request, provider_code, token):
    if request.method not in ("POST", "GET"):
        return HttpResponseNotAllowed(["POST", "GET"])
    provider = CourierProvider.objects.filter(code=provider_code, is_active=True).first()
    if not provider:
        raise Http404
    cred = next((c for c in provider.credentials.filter(is_active=True)
                 if secrets.compare_digest(c.webhook_token, token)), None)

    body = request.body.decode("utf-8", "replace")[:100_000]
    if request.method == "GET" and request.GET:
        body = json.dumps(request.GET.dict())
    elif request.method == "POST" and request.POST:
        body = json.dumps(request.POST.dict())  # form / multipart -> JSON
    headers = {k: v for k, v in request.headers.items()
               if k.lower() not in ("cookie", "authorization")}
    ip = _client_ip(request)

    allowed = (cred.extra or {}).get("webhook_allowed_ips") if cred else None
    ip_ok = True
    if allowed and ip:
        try:
            addr = ipaddress.ip_address(ip)
            ip_ok = any(addr in ipaddress.ip_network(n, strict=False) for n in allowed)
        except ValueError:
            ip_ok = False

    wl = WebhookLog.objects.create(provider=provider, remote_ip=ip, headers=headers, body=body,
                                   authenticated=bool(cred) and ip_ok)
    if not cred or not ip_ok:
        wl.processed = True
        wl.error = "Rejected: bad token" if not cred else f"Rejected: IP {ip} not allowed"
        wl.save(update_fields=["processed", "error"])
        return JsonResponse({"status": 0, "error": "unauthorized"}, status=401)

    if request.method == "GET" and not request.GET:
        # Courier "ping" to verify the URL
        wl.processed = wl.success = True
        wl.save(update_fields=["processed", "success"])
        return JsonResponse({"status": 1, "message": "ok"})

    from .tasks import process_webhook
    transaction.on_commit(lambda: process_webhook.delay(wl.pk))
    return JsonResponse({"status": 1, "message": "received", "id": wl.pk})


@require_GET
def customer_tracking(request, order_number):
    """Tracking timeline for the logged-in customer's own order."""
    if not request.user.is_authenticated:
        return JsonResponse({"error": "login required"}, status=401)
    order = get_object_or_404(Order, order_number=order_number, user=request.user)
    s = Shipment.active_for(order)
    if not s:
        return JsonResponse({"order": order.order_number, "shipment": None})
    return JsonResponse({
        "order": order.order_number,
        "shipment": {
            "courier": s.provider.name, "tracking_number": s.tracking_number,
            "tracking_url": s.tracking_url, "status": s.status,
            "status_label": s.get_status_display(), "courier_status": s.raw_status,
            "booked_at": s.booked_at, "delivered_at": s.delivered_at,
            "events": [{"status": e.get_status_display() if e.status else "",
                        "courier_status": e.raw_status, "description": e.description,
                        "location": e.location, "time": e.event_time}
                       for e in s.events.all()[:50]],
        },
    })


# ---------------------------------------------------------------------------
# Shipping rates (weight-based tariffs the customer is charged with)
# ---------------------------------------------------------------------------
def _tariff_calc(request, tariff):
    """The rate calculator on the page: ?grams=&city=&state="""
    from decimal import Decimal as D

    from .models import ShippingZone
    from .tariffs import charge, origin, province_label, province_of, zone_for
    try:
        grams = max(0, int(request.GET.get("grams") or 0))
    except ValueError:
        grams = 0
    city, state = (request.GET.get("city") or "").strip(), (request.GET.get("state") or "").strip()
    o_city, o_prov = origin(tariff)
    out = {"grams": grams, "city": city, "state": state, "origin_city": o_city,
           "origin_province": province_label(o_prov)}
    if grams:
        out["rows"] = [{"label": z.label, "price": charge(tariff, grams, z)} for z in ShippingZone]
        if city:
            z = zone_for(tariff, city, state)
            out["zone"] = ShippingZone(z).label
            out["dest_province"] = province_label(province_of(city, state)) or "unknown (Zone B used)"
            out["price"] = charge(tariff, grams, z)
            out["kg"] = D(grams) / 1000
    return out


@staff_required
def tariff_list(request):
    from adminpanel.models import StoreSettings

    from .models import ShippingTariff
    s = StoreSettings.get()
    if request.method == "POST" and request.POST.get("action") == "toggle":
        s = StoreSettings.objects.get(pk=s.pk)
        s.weight_shipping_enabled = request.POST.get("enabled") == "1"
        s.updated_by = request.user
        s.save()
        messages.success(request, "Weight-based shipping is now " + ("on." if s.weight_shipping_enabled else "off."))
        return redirect("couriers:tariffs")
    tariffs = list(ShippingTariff.objects.select_related("provider").prefetch_related("slabs"))
    for t in tariffs:
        lo, t.rows = 0, []
        for slab in t.slabs.all():
            t.rows.append({"from": lo, "slab": slab})
            lo = slab.max_grams
    default = ShippingTariff.default()
    return render(request, "couriers/tariffs.html", {
        "tariffs": tariffs, "default": default, "store": s,
        "calc": _tariff_calc(request, default) if default else None,
    })


@staff_required
def tariff_edit(request, pk=None):
    from .forms import SlabFormSet, TariffForm
    from .models import ShippingTariff
    tariff = get_object_or_404(ShippingTariff, pk=pk) if pk else None
    form = TariffForm(request.POST or None, instance=tariff)
    formset = SlabFormSet(request.POST or None, instance=tariff or ShippingTariff(), prefix="slabs")
    if request.method == "POST":
        if form.is_valid() and formset.is_valid():
            with transaction.atomic():
                obj = form.save()
                formset.instance = obj
                formset.save()
            from accounts.error_logging import security_event
            security_event("shipping_tariff_changed", request, severity="INFO", tariff=obj.pk,
                           default=obj.is_default)
            messages.success(request, f"'{obj.name}' saved.")
            return redirect("couriers:tariffs")
        messages.error(request, "Please fix the highlighted fields.")
    return render(request, "couriers/tariff_edit.html", {"form": form, "formset": formset, "tariff": tariff})


@staff_required
@require_POST
def tariff_action(request, pk):
    from .models import ShippingTariff
    t = get_object_or_404(ShippingTariff, pk=pk)
    action = request.POST.get("action")
    if action == "default":
        with transaction.atomic():
            ShippingTariff.objects.filter(is_default=True).update(is_default=False)
            t.is_default, t.is_active = True, True
            t.save(update_fields=["is_default", "is_active", "modified_at"])
        messages.success(request, f"'{t.name}' is now the default tariff.")
    elif action == "delete":
        if t.is_default:
            messages.error(request, "Make another tariff the default before deleting this one.")
        else:
            t.delete()
            messages.success(request, "Tariff deleted.")
    return redirect("couriers:tariffs")
