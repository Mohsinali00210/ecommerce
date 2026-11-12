from django import template
from django.utils.html import format_html

register = template.Library()

COLORS = {
    "booked": "secondary", "picked_up": "info", "in_transit": "primary",
    "out_for_delivery": "warning text-dark", "delivery_failed": "danger", "delivered": "success",
    "return_in_transit": "warning text-dark", "returned": "dark", "cancelled": "light text-dark border",
    "booking_failed": "danger",
}


@register.simple_tag
def shipment_badge(status, label=None):
    return format_html('<span class="badge bg-{}">{}</span>', COLORS.get(status, "secondary"),
                       label or status.replace("_", " ").title())


@register.filter
def get_item(d, key):
    return d.get(key, 0) if hasattr(d, "get") else 0
