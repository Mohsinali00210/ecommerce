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
        "gateway": PaymentGateway.objects.first(),
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
    else:
        messages.error(request, "That action isn't possible for this payment.")
    return redirect("admin_payment_detail", pk=p.pk)


def gateway_settings(request):
    gateway = PaymentGateway.objects.filter(code="safepay").first()
    form = GatewayForm(request.POST or None, instance=gateway)
    if request.method == "POST" and form.is_valid():
        obj = form.save(commit=False)
        obj.code = "safepay"
        obj.save()
        security_event("payment_gateway_changed", request, severity="WARNING", gateway="safepay",
                       environment=obj.environment, active=obj.is_active)
        messages.success(request, "Safepay settings saved.")
        return redirect("admin_payment_gateway")
    return render(request, "payments/admin_gateway.html", {
        "form": form, "gateway": gateway,
        "webhook_url": request.build_absolute_uri(reverse("payments:webhook", args=["safepay"])),
    })
