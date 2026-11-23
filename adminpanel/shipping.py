"""Store-wide shipping rules, shared by the cart, checkout and order placement.

    shipping per line  -> product.shipping_charges + additional (0 if the product ships free)
    cart shipping      -> sum of the lines, capped at StoreSettings.max_shipping_charge
    free shipping      -> 0 when (subtotal - discounts) >= StoreSettings.free_shipping_threshold

The cart page repeats the same rules in JavaScript (values come from rules()).
"""
from decimal import Decimal

ZERO = Decimal("0.00")


def _settings():
    from .models import StoreSettings
    return StoreSettings.get()


def rules():
    s = _settings()
    cap = s.max_shipping_charge or ZERO
    return {
        "free_enabled": bool(s.free_shipping_enabled),
        "free_threshold": s.free_shipping_threshold or ZERO,
        "max_shipping": cap if cap > 0 else None,
    }


def cap(raw_total):
    r = rules()
    raw_total = Decimal(raw_total or 0)
    return min(raw_total, r["max_shipping"]) if r["max_shipping"] is not None else raw_total


def totals(subtotal, discount, shipping_raw):
    """Cart totals with the cap and the free-shipping threshold applied."""
    r = rules()
    subtotal, discount, shipping_raw = Decimal(subtotal), Decimal(discount), Decimal(shipping_raw)
    goods = subtotal - discount
    capped_total = cap(shipping_raw)
    free_by_threshold = bool(r["free_enabled"] and goods > 0 and goods >= r["free_threshold"]
                             and shipping_raw > 0)
    shipping_total = ZERO if free_by_threshold else capped_total
    return {
        "subtotal": subtotal,
        "discount": discount,
        "shipping_raw": shipping_raw,
        "shipping_total": shipping_total,
        "shipping_capped": (not free_by_threshold) and capped_total < shipping_raw,
        "free_shipping_applied": free_by_threshold,
        "free_shipping_threshold": r["free_threshold"] if r["free_enabled"] else None,
        "max_shipping": r["max_shipping"],
        "final_total": goods + shipping_total,
    }


def product_note(product, price):
    """What the product page / quick view says about shipping for this item."""
    r = rules()
    price = Decimal(price or 0)
    if not getattr(product, "shipping_enabled", True):
        return {"kind": "none"}
    if product.free_shipping:
        return {"kind": "free_item"}
    if r["free_enabled"] and r["free_threshold"] > 0:
        if price >= r["free_threshold"]:
            return {"kind": "free_threshold", "threshold": r["free_threshold"]}
        return {"kind": "add_more", "threshold": r["free_threshold"],
                "remaining": r["free_threshold"] - price}
    return {"kind": "paid"}
