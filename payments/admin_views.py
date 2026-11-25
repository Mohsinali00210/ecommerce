from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Count, Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from accounts import rbac
from accounts.error_logging import security_event

from . import services
from .forms import GatewayForm
from .models import Payment, PaymentEvent, PaymentGateway

# Access: /Adminpanel/Payments/ -> view_orders (read) / manage_finance (changes); see accounts/rbac.py


def payments_list(request):
    qs = Payment.objects.select_related("order", "order__user", "gateway")
    status, method, q = request.GET.get("status", ""), request.GET.get("method", ""), request.GET.get("q", "").strip()
    if status == "review":
        qs = qs.filter(method="bank", status="pending", proof_uploaded_at__isnull=False)
    elif status:
        qs = qs.filter(status=status)
    if method:
        qs = qs.filter(method=method)
    if q:
        qs = qs.filter(Q(order__order_number__icontains=q) | Q(reference__icontains=q) | Q(tracker__icontains=q)
                       | Q(order__user__email__icontains=q))
    summary = {r["status"]: r for r in Payment.objects.values("status").annotate(n=Count("id"), total=Sum("amount"))}
    return render(request, "payments/admin_list.html", {
        "page": Paginator(qs, 25).get_page(request.GET.get("page")),
        "f_status": status, "f_method": method, "q": q, "summary": summary,
        "to_review": Payment.objects.filter(method="bank", status="pending", proof_uploaded_at__isnull=False).count(),
        "statuses": Payment.STATUS_CHOICES, "methods": Payment.METHOD_CHOICES,
        "can_manage": rbac.has_admin_perm(request.user, "manage_finance"),
        "gateway": PaymentGateway.objects.filter(is_active=True).first(),
    })


def payment_detail(request, pk):
    p = get_object_or_404(Payment.objects.select_related("order", "order__user", "gateway", "verified_by"), pk=pk)
    return render(request, "payments/admin_detail.html", {
        "p": p, "events": p.events.select_related("created_by")[:100],
        "can_manage": rbac.has_admin_perm(request.user, "manage_finance"),
    })


@require_POST
def payment_action(request, pk):
    p = get_object_or_404(Payment, pk=pk)
    action = request.POST.get("action")
    note = (request.POST.get("note") or "").strip()[:500]
    if action == "mark_paid" and p.status != "paid":
        services.mark_paid(p, reference=request.POST.get("reference", ""), source="admin", user=request.user,
                           data={"note": note})
        security_event("payment_marked_paid", request, severity="WARNING", payment=p.pk, order=p.order_id)
        messages.success(request, "Payment marked as paid.")
    elif action == "reject" and p.status == "pending":
        services.mark_failed(p, reason=note or "Rejected by staff", data={"by": request.user.email})
        messages.success(request, "Payment rejected. The customer can upload a new receipt.")
    elif action == "refunded" and p.status == "paid":
        p.status, p.note = "refunded", note
        p.save(update_fields=["status", "note", "updated_at"])
        p.order.payment_status = "refunded"
        p.order.save()
        PaymentEvent.objects.create(payment=p, kind="refunded", created_by=request.user, data={"note": note})
        security_event("payment_refunded", request, severity="WARNING", payment=p.pk)
        messages.success(request, "Marked as refunded.")
    elif action == "check_status" and p.method == "online" and p.gateway and p.tracker and p.status != "paid":
        adapter = p.gateway.adapter()
        check = getattr(adapter, "check_status", None)
        if not check:
            messages.error(request, f"{p.gateway.name} has no status check. Confirm it in the gateway dashboard.")
        else:
            try:
                res = check(p)
            except Exception as exc:
                messages.error(request, f"Status check failed: {exc}")
            else:
                PaymentEvent.objects.create(payment=p, gateway_code=p.gateway.code, kind=f"status_{res.event}",
                                            verified=res.verified, created_by=request.user,
                                            data={"reason": res.reason, "reference": res.reference})
                if res.event == "paid":
                    services.mark_paid(p, reference=res.reference, source="status_check", user=request.user)
                    messages.success(request, "The gateway confirms this payment. Marked as paid.")
                elif res.event == "failed":
                    services.mark_failed(p, reason=res.reason or "Gateway reports failure")
                    messages.warning(request, "The gateway reports this payment as failed.")
                else:
                    messages.info(request, f"Still pending at the gateway. {res.reason}".strip())
    else:
        messages.error(request, "That action isn't possible for this payment.")
    return redirect("admin_payment_detail", pk=p.pk)


def gateway_settings(request):
    """All gateways: status, switch, links to their settings."""
    from adminpanel.models import StoreSettings
    gateways = list(PaymentGateway.objects.all())
    for g in gateways:
        try:
            g.cls = g.adapter_class()
        except LookupError:
            g.cls = None
    return render(request, "payments/admin_gateways.html", {
        "gateways": gateways, "store": StoreSettings.get(),
        "checkout_methods": services.available_methods(user=request.user),
    })


def gateway_edit(request, code):
    gateway = get_object_or_404(PaymentGateway, code=code)
    try:
        cls = gateway.adapter_class()
    except LookupError:
        messages.error(request, f"No integration code for '{code}'.")
        return redirect("admin_payment_gateway")
    form = GatewayForm(request.POST or None, instance=gateway, adapter_cls=cls)
    if request.method == "POST" and form.is_valid():
        obj = form.save()
        security_event("payment_gateway_changed", request, severity="WARNING", gateway=obj.code,
                       environment=obj.environment, active=obj.is_active)
        PaymentEvent.objects.create(gateway_code=obj.code, kind="gateway_settings_changed", created_by=request.user,
                                    data={"environment": obj.environment, "active": obj.is_active})
        messages.success(request, f"{obj.name} settings saved.")
        return redirect("admin_payment_gateway_edit", code=obj.code)
    return render(request, "payments/admin_gateway.html", {
        "form": form, "gateway": gateway, "cls": cls,
        "webhook_url": request.build_absolute_uri(reverse("payments:webhook", args=[gateway.code]))
        if cls.has_webhook else "",
    })


@require_POST
def gateway_test(request, code):
    gateway = get_object_or_404(PaymentGateway, code=code)
    try:
        msg = gateway.adapter().test_connection()
        ok = True
    except Exception as exc:  # GatewayError, LookupError, network...
        msg, ok = str(exc) or exc.__class__.__name__, False
    PaymentEvent.objects.create(gateway_code=code, kind="gateway_test", verified=ok, created_by=request.user,
                                data={"ok": ok, "message": msg[:500]})
    (messages.success if ok else messages.error)(request, msg)
    return redirect("admin_payment_gateway_edit", code=code)


def payment_logs(request):
    """Every payment event: sessions, returns, webhooks (accepted and rejected), admin actions."""
    qs = PaymentEvent.objects.select_related("payment", "payment__order", "created_by")
    gw, kind, q = request.GET.get("gateway", ""), request.GET.get("kind", ""), request.GET.get("q", "").strip()
    verified = request.GET.get("verified", "")
    if gw:
        qs = qs.filter(gateway_code=gw)
    if kind:
        qs = qs.filter(kind__startswith=kind)
    if verified in ("1", "0"):
        qs = qs.filter(verified=verified == "1")
    if q:
        qs = qs.filter(Q(payment__order__order_number__icontains=q) | Q(payment__reference__icontains=q)
                       | Q(payment__tracker__icontains=q))
    kinds = sorted({k.split("_")[0] for k in PaymentEvent.objects.values_list("kind", flat=True).distinct()})
    return render(request, "payments/admin_logs.html", {
        "page": Paginator(qs, 50).get_page(request.GET.get("page")),
        "f_gateway": gw, "f_kind": kind, "f_verified": verified, "q": q, "kinds": kinds,
        "gateways": PaymentGateway.objects.values_list("code", "name"),
    })


# ---------------------------------------------------------------------------
# Withdrawals: payout methods / charges, payout log, transaction history
# ---------------------------------------------------------------------------
def payout_settings(request):
    from .models import PayoutMethod
    return render(request, "payments/admin_payouts.html", {"methods": PayoutMethod.objects.all()})


def payout_method_edit(request, code):
    from .forms import PayoutMethodForm
    from .models import PayoutMethod
    pm = get_object_or_404(PayoutMethod, code=code)
    form = PayoutMethodForm(request.POST or None, instance=pm)
    if request.method == "POST" and form.is_valid():
        obj = form.save()
        security_event("payout_method_changed", request, severity="WARNING", method=obj.code, mode=obj.mode,
                       provider=obj.provider, enabled=obj.is_enabled)
        messages.success(request, f"{obj.name} payout settings saved.")
        return redirect("admin_payout_settings")
    from decimal import Decimal
    examples = [(a, pm.fee_for(a), a - pm.fee_for(a)) for a in (Decimal("500"), Decimal("1000"), Decimal("5000"), Decimal("20000"))]
    return render(request, "payments/admin_payout_edit.html", {"form": form, "pm": pm, "examples": examples})


def payout_logs(request):
    from .models import PayoutEvent
    qs = PayoutEvent.objects.select_related("withdrawal", "withdrawal__user", "created_by")
    kind, q = request.GET.get("kind", ""), request.GET.get("q", "").strip()
    if kind:
        qs = qs.filter(kind=kind)
    if q:
        qs = qs.filter(Q(withdrawal__user__email__icontains=q) | Q(reference__icontains=q)
                       | Q(withdrawal__account_number__icontains=q))
    return render(request, "payments/admin_payout_logs.html", {
        "page": Paginator(qs, 50).get_page(request.GET.get("page")), "q": q, "f_kind": kind,
        "kinds": PayoutEvent.objects.values_list("kind", flat=True).distinct().order_by("kind"),
    })


def transactions(request):
    from . import history
    kind, q, status = request.GET.get("kind", ""), request.GET.get("q", "").strip(), request.GET.get("status", "")
    return render(request, "payments/admin_transactions.html", {
        "page": Paginator(history.rows(kind=kind, q=q, status=status), 50).get_page(request.GET.get("page")),
        "kinds": history.KINDS, "f_kind": kind, "q": q, "f_status": status, "totals": history.totals(),
    })
