import logging

from django.contrib.auth.decorators import login_required
from django.http import FileResponse, Http404, HttpResponse, HttpResponseBadRequest, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django_ratelimit.decorators import ratelimit

from accounts import rbac
from accounts.error_logging import security_event
from Web.order_emails import order_from_token, order_link

from . import services
from .gateways.base import GatewayError, ReturnResult
from .models import Payment, PaymentEvent, PaymentGateway
from .validators import validate_receipt

log = logging.getLogger("app")


def _message(request, title, text, order=None, status=200):
    return render(request, "payments/message.html",
                  {"title": title, "text": text, "order_url": order_link(order) if order else "/"}, status=status)


def _after_payment_url(request, order):
    if request.user.is_authenticated and order.user_id == request.user.id:
        return f"{reverse('OrderConfirmation')}?order_id={order.pk}"
    return order_link(order)


# ---------------------------------------------------------------------------
# Customer: pay / return / cancel
# ---------------------------------------------------------------------------
def _go(request, session):
    """Send the browser to the gateway: plain redirect, or an auto-submitted POST form."""
    if session.post_fields:
        resp = render(request, "payments/redirect_post.html",
                      {"action": session.redirect_url, "fields": session.post_fields})
        resp["Cache-Control"] = "no-store"
        return resp
    return redirect(session.redirect_url)


@ratelimit(key="ip", rate="20/10m", block=True)
def pay(request, token):
    """Start (or retry) the online payment for an order. Works from the email link."""
    order, problem = order_from_token(token)
    if not order:
        return _message(request, "Link not valid", "This payment link is invalid or has expired.", status=404)
    payment = services.latest(order)
    if payment and payment.status == "paid":
        return redirect(_after_payment_url(request, order))
    if not payment or payment.method != "online":
        return _message(request, "Nothing to pay online", "This order doesn't use online payment.", order)
    try:
        session = services.start_online(payment, request)
    except services.PaymentNotAllowed as exc:
        return _message(request, "Payment unavailable", str(exc), order, status=409)
    return _go(request, session)


HIDDEN_RETURN_FIELDS = {"sig", "pp_SecureHash", "pp_Password", "merchantHashedReq", "auth_token", "result"}


@csrf_exempt  # gateways post back here; each adapter verifies the data (signature or server-side check)
@ratelimit(key="ip", rate="30/10m", block=True)
def payment_return(request, pk):
    payment = get_object_or_404(Payment.objects.select_related("order", "gateway", "order__user"), pk=pk,
                                method="online")
    data = request.POST.dict() or request.GET.dict()
    order = payment.order
    if payment.status == "paid":
        return redirect(_after_payment_url(request, order))
    gateway = payment.gateway
    if not gateway:
        return _message(request, "Payment not found", "We couldn't match this payment.", order, status=400)
    try:
        result = gateway.adapter().handle_return(payment, data)
    except GatewayError as exc:
        result = ReturnResult("pending", reason=str(exc))
    PaymentEvent.objects.create(payment=payment, gateway_code=gateway.code, kind=f"return_{result.event}",
                                verified=result.verified,
                                data={"reason": result.reason, "reference": result.reference,
                                      **{k: v for k, v in data.items() if k not in HIDDEN_RETURN_FIELDS}})
    if result.event == "redirect" and result.session:
        return _go(request, result.session)
    if result.event == "paid":
        services.mark_paid(payment, reference=result.reference, source="return",
                           data={"gateway": gateway.code})
        return redirect(_after_payment_url(request, order))
    if result.event in ("failed", "cancelled"):
        services.mark_failed(payment, status=result.event, reason=result.reason or "Payment not completed",
                             data={"via": "return"})
        return _message(request, "Payment not completed",
                        (result.reason + ". " if result.reason else "") +
                        "No money was taken. You can try again from your order page before the order expires.",
                        order)
    if data.get("sig") or data.get("pp_SecureHash"):
        security_event("payment_signature_invalid", request, severity="WARNING", payment=payment.pk)
    # Not verifiable here - the webhook / status check may still confirm it.
    return _message(request, "Confirming your payment",
                    "We're waiting for confirmation from the payment provider. "
                    "You'll get an email as soon as it's confirmed - no need to pay again.", order)


def payment_cancel(request, pk):
    payment = get_object_or_404(Payment.objects.select_related("order"), pk=pk, method="online")
    if payment.status == "pending":
        services.mark_failed(payment, status="cancelled", reason="Customer cancelled at the gateway")
    return _message(request, "Payment cancelled",
                    "No money was taken. You can try again from your order page before the order expires.",
                    payment.order)


@csrf_exempt
@require_POST
def webhook(request, code):
    gateway = PaymentGateway.objects.filter(code=code).first()
    if not gateway:
        raise Http404
    adapter = gateway.adapter()
    try:
        result = adapter.parse_webhook(request.body, request.headers)
    except (GatewayError, ValueError) as exc:
        PaymentEvent.objects.create(gateway_code=code, kind="webhook_rejected", verified=False,
                                    data={"error": str(exc), "body": request.body[:2000].decode("utf-8", "replace")})
        security_event("payment_webhook_rejected", request, severity="WARNING", gateway=code)
        return HttpResponseBadRequest("invalid signature")
    payment = Payment.objects.filter(gateway=gateway, tracker=result.tracker).first() if result.tracker else None
    PaymentEvent.objects.create(payment=payment, gateway_code=code, kind=f"webhook_{result.event}",
                                verified=True, data=result.raw)
    if payment and result.event == "paid":
        services.mark_paid(payment, reference=result.reference, source="webhook")
    elif payment and result.event == "failed":
        services.mark_failed(payment, reason="Gateway reported failure", data={"via": "webhook"})
    ack = getattr(adapter, "webhook_ack", None)
    if ack:
        body, ctype = ack()
        return HttpResponse(body, content_type=ctype)
    return HttpResponse("ok")


# ---------------------------------------------------------------------------
# Test gateway (sandbox simulator)
# ---------------------------------------------------------------------------
@ratelimit(key="ip", rate="30/10m", block=True)
def test_gateway(request, token):
    from .gateways.testgateway import sign, unsign
    info = unsign(token)
    if not info:
        return _message(request, "Link expired", "This test payment link is invalid or has expired.", status=404)
    payment = get_object_or_404(Payment.objects.select_related("order", "gateway"), pk=info["p"], method="online")
    if not payment.gateway or payment.gateway.code != "test" or payment.tracker != info["t"]:
        raise Http404
    if request.method == "POST":
        outcome = request.POST.get("outcome")
        if outcome == "cancel":
            return redirect(info["c"])
        result = sign({"p": payment.pk, "t": payment.tracker, "outcome": "paid" if outcome == "paid" else "failed"})
        return render(request, "payments/redirect_post.html", {"action": info["r"], "fields": {"result": result}})
    return render(request, "payments/test_gateway.html", {"payment": payment, "order": payment.order})


# ---------------------------------------------------------------------------
# Customer: bank transfer receipt
# ---------------------------------------------------------------------------
@login_required
@require_POST
@ratelimit(key="user", rate="10/h", block=True)
def upload_proof(request, pk):
    payment = get_object_or_404(Payment.objects.select_related("order"), pk=pk, order__user=request.user,
                                method="bank")
    if payment.status not in ("pending", "failed"):
        return JsonResponse({"success": False, "message": "This payment is already settled."}, status=400)
    f = request.FILES.get("proof")
    try:
        validate_receipt(f)
    except ValueError as exc:
        return JsonResponse({"success": False, "message": str(exc)}, status=400)
    if payment.proof:
        payment.proof.delete(save=False)
    payment.proof = f
    payment.proof_uploaded_at = timezone.now()
    payment.status = "pending"
    payment.save()
    PaymentEvent.objects.create(payment=payment, kind="proof_uploaded", created_by=request.user,
                                data={"name": f.name, "size": f.size})
    return JsonResponse({"success": True, "message": "Receipt uploaded. We'll confirm your payment shortly."})


@login_required
def view_proof(request, pk):
    payment = get_object_or_404(Payment.objects.select_related("order"), pk=pk)
    owner = payment.order.user_id == request.user.id
    if not owner and not rbac.has_admin_perm(request.user, "view_orders"):
        raise Http404
    if not payment.proof:
        raise Http404
    resp = FileResponse(payment.proof.open("rb"), as_attachment=False,
                        filename=payment.proof.name.rsplit("/", 1)[-1])
    resp["X-Content-Type-Options"] = "nosniff"
    resp["Content-Security-Policy"] = "default-src 'none'; img-src 'self'; style-src 'unsafe-inline'"
    resp["Cache-Control"] = "private, no-store"
    return resp
