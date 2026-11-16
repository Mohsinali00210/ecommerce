"""Dashboard figures. All queries are aggregate SQL, one call per widget."""
from datetime import datetime, time, timedelta
from decimal import Decimal

from django.db.models import Avg, Count, DecimalField, F, Q, Sum, Value
from django.db.models.functions import Coalesce, ExtractHour, TruncDate, TruncMonth, TruncWeek
from django.utils import timezone

from accounts.models import SecurityEvent, User
from products.models import Category, Product, ProductVariant
from Web.models import Order, OrderItem, OrderRequest, SupportTicket

LOST_STATUSES = ("cancelled", "returned", "return_in_transit")
OPEN_STATUSES = ("pending", "submited", "processing", "ordersuccessfull")
PRESETS = {"today": 0, "7d": 6, "30d": 29, "90d": 89, "365d": 364}
ZERO = Value(Decimal("0"), output_field=DecimalField(max_digits=14, decimal_places=2))


def resolve_range(params):
    """(start, end, label) from ?range=7d or ?from=YYYY-MM-DD&to=YYYY-MM-DD. Max 2 years."""
    tz = timezone.get_current_timezone()
    today = timezone.localdate()
    key = params.get("range", "30d")
    start_d = end_d = None
    if key == "custom":
        try:
            start_d = datetime.strptime(params.get("from", ""), "%Y-%m-%d").date()
            end_d = datetime.strptime(params.get("to", ""), "%Y-%m-%d").date()
        except ValueError:
            key = "30d"
        else:
            if start_d > end_d:
                start_d, end_d = end_d, start_d
            end_d = min(end_d, today)
            start_d = max(start_d, end_d - timedelta(days=730))
    if key == "month":
        start_d, end_d = today.replace(day=1), today
    elif key != "custom":
        key = key if key in PRESETS else "30d"
        start_d, end_d = today - timedelta(days=PRESETS[key]), today
    start = timezone.make_aware(datetime.combine(start_d, time.min), tz)
    end = timezone.make_aware(datetime.combine(end_d, time.max), tz)
    return start, end, key


def _pct(cur, prev):
    cur, prev = float(cur or 0), float(prev or 0)
    if prev == 0:
        return None if cur == 0 else 100.0
    return round((cur - prev) / prev * 100, 1)


def _orders(start, end):
    return Order.objects.filter(created_at__range=(start, end), is_deleted=False)


def _kpis(start, end):
    qs = _orders(start, end)
    agg = qs.aggregate(
        orders=Count("id"),
        revenue=Coalesce(Sum("total_amount", filter=~Q(status__in=LOST_STATUSES)), ZERO),
        lost=Count("id", filter=Q(status__in=LOST_STATUSES)),
        delivered=Count("id", filter=Q(status="delivered")),
    )
    paid_orders = agg["orders"] - agg["lost"]
    agg["aov"] = (agg["revenue"] / paid_orders) if paid_orders else Decimal("0")
    agg["items"] = (OrderItem.objects.filter(order__in=qs.exclude(status__in=LOST_STATUSES))
                    .aggregate(n=Coalesce(Sum("quantity"), 0))["n"])
    agg["customers"] = User.objects.filter(date_joined__range=(start, end), is_staff=False).count()
    agg["buyers"] = qs.exclude(user__isnull=True).values("user").distinct().count()
    agg["loss_rate"] = round(agg["lost"] / agg["orders"] * 100, 1) if agg["orders"] else 0
    return agg


def kpis(start, end):
    span = end - start
    prev_end = start - timedelta(microseconds=1)
    prev_start = prev_end - span
    cur, prev = _kpis(start, end), _kpis(prev_start, prev_end)
    cards = []
    for key, label, fmt, icon in [
        ("revenue", "Revenue", "money", "bi-cash-stack"),
        ("orders", "Orders", "int", "bi-bag-check"),
        ("aov", "Avg. order value", "money", "bi-receipt"),
        ("items", "Items sold", "int", "bi-box-seam"),
        ("customers", "New customers", "int", "bi-person-plus"),
        ("loss_rate", "Cancel / return rate", "pct", "bi-arrow-counterclockwise"),
    ]:
        change = _pct(cur[key], prev[key])
        cards.append({"key": key, "label": label, "value": float(cur[key]), "format": fmt, "icon": icon,
                      "previous": float(prev[key]), "change": change,
                      # for the loss rate, going down is good
                      "good": None if change is None else (change <= 0 if key == "loss_rate" else change >= 0)})
    snapshot = {
        "open_orders": Order.objects.filter(status__in=OPEN_STATUSES, is_deleted=False).count(),
        "pending_requests": OrderRequest.objects.filter(status__iexact="pending").count(),
        "open_tickets": SupportTicket.objects.exclude(status__in=["closed", "resolved", "Closed",
                                                                  "Resolved"]).count(),
        "low_stock": ProductVariant.objects.filter(is_deleted=False, is_active=True,
                                                   stock_quantity__lte=5,
                                                   product__is_deleted=False).count(),
        "out_of_stock": ProductVariant.objects.filter(is_deleted=False, is_active=True, stock_quantity=0,
                                                      product__is_deleted=False).count(),
        "products": Product.objects.filter(is_deleted=False).count(),
        "customers_total": User.objects.filter(is_staff=False).count(),
    }
    return cards, snapshot


def _bucket(start, end):
    days = (end - start).days + 1
    if days <= 62:
        return TruncDate, "day"
    if days <= 366:
        return TruncWeek, "week"
    return TruncMonth, "month"


def _date_axis(start, end, unit):
    out, d = [], start.date() if hasattr(start, "date") else start
    last = end.date()
    if unit == "week":
        d = d - timedelta(days=d.weekday())
    if unit == "month":
        d = d.replace(day=1)
    while d <= last:
        out.append(d)
        if unit == "day":
            d += timedelta(days=1)
        elif unit == "week":
            d += timedelta(days=7)
        else:
            d = (d.replace(day=28) + timedelta(days=4)).replace(day=1)
    return out


def _as_date(v):
    return v.date() if hasattr(v, "date") and callable(v.date) else v


def trends(start, end):
    trunc, unit = _bucket(start, end)
    tz = timezone.get_current_timezone()
    rows = (_orders(start, end).annotate(b=trunc("created_at", tzinfo=tz)).values("b")
            .annotate(revenue=Coalesce(Sum("total_amount", filter=~Q(status__in=LOST_STATUSES)), ZERO),
                      orders=Count("id")).order_by("b"))
    users = (User.objects.filter(date_joined__range=(start, end), is_staff=False)
             .annotate(b=trunc("date_joined", tzinfo=tz)).values("b").annotate(n=Count("id")))
    by_rev = {_as_date(r["b"]): r for r in rows}
    by_usr = {_as_date(r["b"]): r["n"] for r in users}
    axis = _date_axis(start, end, unit)
    fmt = {"day": "%d %b", "week": "%d %b", "month": "%b %Y"}[unit]
    return {
        "unit": unit,
        "labels": [d.strftime(fmt) for d in axis],
        "revenue": [float(by_rev[d]["revenue"]) if d in by_rev else 0 for d in axis],
        "orders": [by_rev[d]["orders"] if d in by_rev else 0 for d in axis],
        "customers": [by_usr.get(d, 0) for d in axis],
    }


def breakdowns(start, end):
    qs = _orders(start, end)
    labels = dict(Order.ORDER_STATUS)
    status = [{"label": labels.get(r["status"], r["status"]), "key": r["status"], "value": r["n"]}
              for r in qs.values("status").annotate(n=Count("id")).order_by("-n")]
    payment = [{"label": (r["payment_method"] or "unknown").upper(), "value": r["n"]}
               for r in qs.values("payment_method").annotate(n=Count("id")).order_by("-n")]
    items = OrderItem.objects.filter(order__in=qs.exclude(status__in=LOST_STATUSES))
    top_products = [{"label": r["product__name"] or "Deleted product", "qty": r["qty"], "value": float(r["rev"])}
                    for r in items.values("product__name")
                    .annotate(qty=Sum("quantity"), rev=Coalesce(Sum("total"), ZERO)).order_by("-rev")[:8]]
    categories = [{"label": r["product__category__name"] or "Uncategorised", "value": float(r["rev"])}
                  for r in items.values("product__category__name")
                  .annotate(rev=Coalesce(Sum("total"), ZERO)).order_by("-rev")[:8]]
    tz = timezone.get_current_timezone()
    hours = {r["h"]: r["n"] for r in qs.annotate(h=ExtractHour("created_at", tzinfo=tz))
             .values("h").annotate(n=Count("id"))}
    return {"status": status, "payment": payment, "top_products": top_products,
            "categories": categories, "hours": [hours.get(h, 0) for h in range(24)]}


def recent(limit=8):
    orders = [{"id": o.pk, "number": o.order_number, "customer": (o.user.full_name or o.user.email) if o.user else "Guest",
               "total": float(o.total_amount or 0), "status": o.status, "status_label": o.get_status_display(),
               "when": o.created_at}
              for o in Order.objects.filter(is_deleted=False).select_related("user").order_by("-created_at")[:limit]]
    customers = [{"name": u.full_name or u.email, "email": u.email, "when": u.date_joined}
                 for u in User.objects.filter(is_staff=False).order_by("-date_joined")[:limit]]
    low_stock = [{"product": v.product.name, "variant": v.name, "stock": v.stock_quantity, "product_id": v.product_id}
                 for v in ProductVariant.objects.filter(is_deleted=False, is_active=True, stock_quantity__lte=5,
                                                        product__is_deleted=False)
                 .select_related("product").order_by("stock_quantity")[:limit]]
    activity = [{"event": e.event, "user": e.username or (e.user.email if e.user else ""), "ip": e.ip_address,
                 "severity": e.severity, "when": e.created_at}
                for e in SecurityEvent.objects.select_related("user").order_by("-created_at")[:limit]]
    return {"orders": orders, "customers": customers, "low_stock": low_stock, "activity": activity}


def build(params):
    start, end, key = resolve_range(params)
    cards, snapshot = kpis(start, end)
    return {
        "range": {"key": key, "from": start.date().isoformat(), "to": end.date().isoformat()},
        "kpis": cards, "snapshot": snapshot, "trends": trends(start, end),
        "breakdowns": breakdowns(start, end), "recent": recent(),
    }
