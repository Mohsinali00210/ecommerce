from django import template

from payments.services import available_methods

register = template.Library()


@register.inclusion_tag("payments/_checkout_options.html", takes_context=True)
def checkout_payment_options(context, total=None):
    request = context.get("request")
    methods = available_methods(total, user=getattr(request, "user", None))
    # Cash on delivery is pre-selected whenever it is available
    first = next((m["value"] for m in methods if m["available"]), None)
    return {"methods": methods, "first": first}


@register.inclusion_tag("payments/_order_payment.html", takes_context=True)
def order_payment_box(context, order):
    from adminpanel.models import StoreSettings
    from payments.services import latest
    from Web.order_emails import order_token
    return {"order": order, "payment": latest(order), "token": order_token(order),
            "bank_details": StoreSettings.get().bank_transfer_details, "csrf_token": context.get("csrf_token")}
