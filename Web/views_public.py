"""Order page opened from the email link - no sign-in needed (signed, expiring token)."""
from django.shortcuts import redirect, render
from django_ratelimit.decorators import ratelimit

from .order_emails import _steps, order_from_token, order_token


@ratelimit(key="ip", rate="60/10m", block=True)
def order_public(request, token):
    order, problem = order_from_token(token)
    if order is None:
        return render(request, "Web/order_public.html", {"problem": problem}, status=404 if problem == "invalid" else 410)
    # The owner, signed in, gets the full account page.
    if request.user.is_authenticated and order.user_id == request.user.id:
        return redirect("home:order-detail", order.order_number)
    shipment = None
    try:
        from couriers.models import Shipment
        shipment = Shipment.active_for(order)
    except Exception:
        pass
    payment = None
    try:
        from payments.models import Payment
        payment = Payment.objects.filter(order=order).order_by("-created_at").first()
    except Exception:
        pass
    return render(request, "Web/order_public.html", {
        "order": order,
        "items": order.items.select_related("product", "variant").prefetch_related("product__images"),
        "steps": _steps(order.status),
        "shipment": shipment,
        "events": shipment.events.exclude(source="manual")[:20] if shipment else [],
        "payment": payment,
        "token": order_token(order),
    })
