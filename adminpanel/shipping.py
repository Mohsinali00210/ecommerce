"""Store-wide shipping rules, shared by the cart, checkout, order placement and product pages.

    free item          -> product.free_shipping: the line adds nothing
    weight-based       -> (Store settings > Weight-based shipping on, default tariff exists)
                          every non-free item that has a weight adds weight x qty to ONE parcel,
                          priced from the tariff for the destination zone (couriers/tariffs.py)
    flat               -> items without a weight: product.shipping_charges + additional
    cap                -> cart shipping never above StoreSettings.max_shipping_charge
    free threshold     -> 0 when free shipping is enabled and (subtotal - discounts) >= threshold

No destination yet (cart page, guest) -> Zone B price, shown as an estimate.
The cart page repeats the same rules in JavaScript (values come from browser_rules()).
"""
from decimal import Decimal

ZERO = Decimal("0.00")


def _settings():
    from .models import StoreSettings
    return StoreSettings.get()


def tariff():
    """Default tariff when weight-based shipping is on, else None."""
    if not getattr(_settings(), "weight_shipping_enabled", False):
        return None
    try:
        from couriers.tariffs import default_tariff
        t = default_tariff()
    except Exception:  # couriers tables not migrated yet
        return None
    return t if t and t.slabs.exists() else None


def rules():
    s = _settings()
    cap = s.max_shipping_charge or ZERO
    return {
        "free_enabled": bool(s.free_shipping_enabled),
        "free_threshold": s.free_shipping_threshold or ZERO,
        "max_shipping": cap if cap > 0 else None,
        "weight_enabled": bool(getattr(s, "weight_shipping_enabled", False)),
    }


def cap(raw_total):
    r = rules()
    raw_total = Decimal(raw_total or 0)
    return min(raw_total, r["max_shipping"]) if r["max_shipping"] is not None else raw_total


# ---------------------------------------------------------------------------
# Destination / zone
# ---------------------------------------------------------------------------
def destination_of(address):
    """Address model, dict or None -> {"city", "state"} or None."""
    if not address:
        return None
    if isinstance(address, dict):
        city, state = address.get("city", ""), address.get("state", "")
    else:
        city, state = getattr(address, "city", ""), getattr(address, "state", "") or ""
    city = (city or "").strip()
    return {"city": city, "state": (state or "").strip()} if city else None


def zone_info(t, destination):
    from couriers.models import ShippingZone
    from couriers.tariffs import zone_for
    dest = destination_of(destination)
    zone = zone_for(t, dest["city"], dest["state"]) if dest else None
    return {
        "zone": zone or ShippingZone.OTHER_PROVINCE,
        "zone_label": ShippingZone(zone or ShippingZone.OTHER_PROVINCE).label,
        "estimated": zone is None,
        "city": dest["city"] if dest else "",
    }


# ---------------------------------------------------------------------------
# Lines and totals
# ---------------------------------------------------------------------------
def line_weight_grams(product, variant=None, qty=1):
    """Weight this line adds to the parcel (0 = free item or no weight set)."""
    if product.free_shipping:
        return 0
    from couriers.tariffs import grams_of
    w = getattr(variant, "weight", None) if variant is not None else None
    grams = grams_of(w) if w else grams_of(product.weight)
    return grams * int(qty or 1)


def totals(subtotal, discount, shipping_raw, weight_charge=None):
    """Cart totals with the cap and the free-shipping threshold applied.
    `shipping_raw` already includes `weight_charge` when there is one."""
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


def summarize(lines, destination=None):
    """Totals for price_cart_item() results. Each line has "shipping" (flat) and, optionally,
    "weight_grams" (0 when the item ships free or has no weight)."""
    subtotal = sum((l["line_original"] for l in lines), ZERO)
    discount = sum((l["line_saved"] for l in lines), ZERO)
    t = tariff()
    grams, flat = 0, ZERO
    for l in lines:
        g = int(l.get("weight_grams") or 0)
        if t and g > 0:
            grams += g
        else:
            flat += Decimal(l["shipping"] or 0)
    weight_charge, zinfo = ZERO, None
    if t and grams > 0:
        from couriers.tariffs import charge
        zinfo = zone_info(t, destination)
        weight_charge = charge(t, grams, zinfo["zone"])
    out = totals(subtotal, discount, flat + weight_charge)
    out.update({
        "weight_based": bool(t and grams > 0),
        "weight_grams": grams,
        "weight_kg": Decimal(grams) / 1000,
        "weight_charge": weight_charge,
        "flat_shipping": flat,
        "shipping_zone": zinfo["zone"] if zinfo else "",
        "shipping_zone_label": zinfo["zone_label"] if zinfo else "",
        "shipping_estimated": bool(zinfo and zinfo["estimated"]),
        "shipping_city": zinfo["city"] if zinfo else "",
        "tariff_name": t.name if t and grams > 0 else "",
    })
    return out


def browser_rules(destination=None):
    """What the cart page's JavaScript needs to repeat summarize()."""
    r = rules()
    t = tariff()
    out = {
        "max_shipping": float(r["max_shipping"]) if r["max_shipping"] is not None else None,
        "free_threshold": float(r["free_threshold"]) if r["free_enabled"] else None,
        "weight": None,
    }
    if t:
        from couriers.tariffs import browser_table
        z = zone_info(t, destination)
        out["weight"] = {**browser_table(t, z["zone"]), "zone_label": z["zone_label"],
                         "estimated": z["estimated"], "city": z["city"]}
    return out


# ---------------------------------------------------------------------------
# Product page / quick view / feeds
# ---------------------------------------------------------------------------
def product_note(product, price, destination=None):
    """What the product page / quick view says about shipping for this item."""
    r = rules()
    price = Decimal(price or 0)
    if not getattr(product, "shipping_enabled", True):
        return {"kind": "none"}
    if product.free_shipping:
        return {"kind": "free_item"}
    note = {"kind": "paid"}
    if r["free_enabled"] and r["free_threshold"] > 0:
        if price >= r["free_threshold"]:
            return {"kind": "free_threshold", "threshold": r["free_threshold"]}
        note = {"kind": "add_more", "threshold": r["free_threshold"],
                "remaining": r["free_threshold"] - price}
    t = tariff()
    grams = line_weight_grams(product)
    if t and grams > 0:
        from couriers.models import ShippingZone
        from couriers.tariffs import all_zone_charges
        charges = all_zone_charges(t, grams)
        if r["max_shipping"] is not None:
            charges = {k: min(v, r["max_shipping"]) for k, v in charges.items()}
        z = zone_info(t, destination)
        note["weight"] = {
            "grams": grams, "kg": Decimal(grams) / 1000,
            "rows": [{"zone": zz.value, "label": zz.label, "price": charges[zz.value]} for zz in ShippingZone],
            "min": min(charges.values()), "max": max(charges.values()),
            "yours": None if z["estimated"] else charges[z["zone"]],
            "your_zone": "" if z["estimated"] else z["zone_label"], "city": z["city"],
        }
    else:
        flat = (product.shipping_charges or ZERO) + (product.additional_shipping_charges or ZERO)
        note["flat"] = cap(flat)
    return note


def product_shipping_price(product, price):
    """Single nationwide shipping price for feeds (Google): the highest zone, so the
    listed price is never lower than what checkout charges."""
    r = rules()
    if product.free_shipping or (r["free_enabled"] and Decimal(price or 0) >= r["free_threshold"]):
        return ZERO
    t = tariff()
    grams = line_weight_grams(product)
    if t and grams > 0:
        from couriers.tariffs import all_zone_charges
        ship = max(all_zone_charges(t, grams).values())
    else:
        ship = (product.shipping_charges or ZERO) + (product.additional_shipping_charges or ZERO)
    return cap(ship)
