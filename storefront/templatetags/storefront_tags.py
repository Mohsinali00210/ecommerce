from decimal import Decimal

from django import template

from adminpanel import shipping

from storefront.models import HomeFeature
from storefront.seo import page_meta

register = template.Library()


@register.inclusion_tag("storefront/seo_head.html", takes_context=True)
def seo_head(context):
    """All SEO tags for the page: title, description, canonical, robots, OG, Twitter, JSON-LD."""
    try:
        meta = page_meta(context)
    except Exception:  # SEO must never break a page
        from accounts.error_logging import log_error
        log_error(context.get("request"), message="SEO tags could not be built")
        meta = {"title": "Shan Zee", "description": "", "canonical": "", "robots": "index, follow", "ld": ""}
    return {"meta": meta}


@register.inclusion_tag("storefront/home_features.html")
def home_features():
    rules = shipping.rules()
    threshold = rules["free_threshold"]
    label = f"{threshold:,.0f}" if threshold else ""
    items = []
    for f in HomeFeature.active():
        items.append({"icon": f.icon if f.icon.startswith("bi-") else f"bi-{f.icon}", "title": f.title,
                      "subtitle": f.subtitle.replace("{threshold}", label), "link": f.link_url})
    return {"features": items}


@register.inclusion_tag("storefront/shipping_note.html", takes_context=True)
def shipping_note(context, product, price, price_element_id=""):
    """Shipping line for the product page and quick view (free item, free-shipping threshold,
    weight-based charge by zone, or the flat charge).
    `price_element_id`: element whose text changes when a variant is picked."""
    try:
        price = Decimal(str(price or 0))
    except Exception:
        price = Decimal("0")
    destination = None
    request = context.get("request")
    user = getattr(request, "user", None)
    if user is not None and user.is_authenticated:
        try:
            from accounts.models import Address
            destination = (Address.objects.filter(user=user, is_default=True).first()
                           or Address.objects.filter(user=user).first())
        except Exception:
            destination = None
    try:
        note = shipping.product_note(product, price, destination)
    except Exception:  # shipping info must never break the product page
        note = {"kind": "paid"}
    item_charge = note.get("flat")
    if item_charge is None:
        item_charge = (product.shipping_charges or Decimal("0")) + (product.additional_shipping_charges or Decimal("0"))
    return {"note": note, "product": product, "item_charge": item_charge, "price_el": price_element_id,
            "threshold": note.get("threshold"), "weight": note.get("weight"),
            "uid": f"shipz{product.pk}{price_element_id}"}
