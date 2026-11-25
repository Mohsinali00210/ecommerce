"""Google Merchant API (products v1): show the shop's products in Google Shopping / free listings.

  insert  POST   https://merchantapi.googleapis.com/products/v1/accounts/{account}/productInputs:insert
                 ?dataSource=accounts/{account}/dataSources/{dataSource}       body: ProductInput
                 (same contentLanguage + feedLabel + offerId = replaces the earlier version)
  delete  DELETE https://merchantapi.googleapis.com/products/v1/accounts/{account}/productInputs/
                 {contentLanguage}~{feedLabel}~{offerId}?dataSource=...
                 (unpadded base64url of that string when the offer id contains / % or ~)
  auth    OAuth2 service account, scope https://www.googleapis.com/auth/content
          (same JSON key as SEO > Google Indexing; add its e-mail as a user in Merchant Center)

Setup: Merchant Center > Settings > Data sources > Add product source > "Add products using API",
copy its ID into SEO settings > Merchant API, with the account ID.
The XML feed (/feeds/google-merchant.xml) keeps working too; use one or the other per data source.
"""
import base64
import logging
from decimal import Decimal

import requests
from django.utils import timezone

from . import seo
from .indexing import IndexingError, _google_token, _record, parse_service_account
from .models import MerchantProduct, SeoSettings

log = logging.getLogger("storefront.merchant")

API = "https://merchantapi.googleapis.com/products/v1"
SCOPE = "https://www.googleapis.com/auth/content"
TIMEOUT = 20


class MerchantError(Exception):
    pass


def _micros(amount):
    return str(int((Decimal(amount) * 1_000_000).to_integral_value()))


def _price(amount):
    return {"amountMicros": _micros(amount), "currencyCode": "PKR"}


def offer_id(product):
    return str(product.sku or product.pk)[:50]


def product_input(product, s=None):
    """ProductInput JSON for one product (also shown in the admin preview)."""
    from adminpanel import shipping
    s = s or SeoSettings.get()
    images = seo.product_images(product, limit=11)
    final, was = seo.product_price(product)
    cats = [c for c in product.category.all() if not c.is_deleted]
    brand = getattr(product.brand, "name", "") or s.merchant_default_brand or s.site_name
    if getattr(product, "available_for_preorder", False):
        availability = "PREORDER"
    else:
        availability = "IN_STOCK" if seo.in_stock(product) else "OUT_OF_STOCK"
    attrs = {
        "title": (product.name or "")[:150],
        "description": seo.clean_text(product.description or product.brief_description or product.name, 5000),
        "link": seo.product_url(product),
        "availability": availability,
        "condition": "NEW",
        "price": _price(was if was else final),
        "brand": brand[:70],
        "mpn": str(product.sku or "")[:70],
        "identifierExists": False,
        "shipping": [{"country": (s.country or "PK")[:2].upper(),
                      "price": _price(shipping.product_shipping_price(product, final))}],
    }
    if images:
        attrs["imageLink"] = images[0]
        if len(images) > 1:
            attrs["additionalImageLinks"] = images[1:11]
    if was:
        attrs["salePrice"] = _price(final)
    if cats:
        attrs["productTypes"] = [" > ".join(c.name for c in cats[:3])]
    if s.merchant_google_category:
        attrs["googleProductCategory"] = s.merchant_google_category
    if product.weight and product.weight > 0:
        attrs["shippingWeight"] = {"value": float(product.weight), "unit": "kg"}
    return {
        "offerId": offer_id(product),
        "contentLanguage": (s.merchant_content_language or "en").lower(),
        "feedLabel": (s.merchant_feed_label or "PK").upper(),
        "productAttributes": attrs,
    }


def _config(s):
    if not (s.merchant_account_id and s.merchant_data_source_id):
        raise MerchantError("Enter the Merchant Center account ID and API data source ID first.")
    info = parse_service_account(s.google_service_account)
    return s.merchant_account_id.strip(), s.merchant_data_source_id.strip(), _google_token(info, SCOPE)


def _error_text(r):
    try:
        return r.json().get("error", {}).get("message", "")[:500] or f"HTTP {r.status_code}"
    except ValueError:
        return f"HTTP {r.status_code}"


HINTS = {401: "Google refused the service account token.",
         403: "Permission denied: add the service account e-mail as a user (Standard / Admin) in Merchant "
              "Center, and enable the Merchant API in Google Cloud."}


def _status(product, oid, status, message=""):
    MerchantProduct.objects.update_or_create(product=product, defaults={
        "offer_id": oid, "status": status, "message": message[:2000], "synced_at": timezone.now()})


def upsert(product, s=None):
    """Insert / replace one product. Returns (ok, message)."""
    s = s or SeoSettings.get()
    oid = offer_id(product)
    try:
        account, source, token = _config(s)
    except (MerchantError, IndexingError) as exc:
        _status(product, oid, "error", str(exc))
        return False, str(exc)
    body = product_input(product, s)
    if "imageLink" not in body["productAttributes"]:
        _status(product, oid, "error", "Not sent: the product has no image (Google requires one).")
        return False, "No image"
    try:
        r = requests.post(f"{API}/accounts/{account}/productInputs:insert", timeout=TIMEOUT, json=body,
                          params={"dataSource": f"accounts/{account}/dataSources/{source}"},
                          headers={"Authorization": f"Bearer {token}"})
    except requests.RequestException as exc:
        msg = f"Could not reach Google: {exc.__class__.__name__}"
        _status(product, oid, "error", msg)
        return False, msg
    if r.status_code == 200:
        _status(product, oid, "synced", "Sent. Google may take a few minutes to process it.")
        return True, "Sent"
    msg = HINTS.get(r.status_code, "") + " " + _error_text(r)
    _status(product, oid, "error", msg.strip())
    return False, msg.strip()


def delete(product, s=None):
    s = s or SeoSettings.get()
    oid = offer_id(product)
    try:
        account, source, token = _config(s)
    except (MerchantError, IndexingError) as exc:
        return False, str(exc)
    lang, label = (s.merchant_content_language or "en").lower(), (s.merchant_feed_label or "PK").upper()
    name = f"{lang}~{label}~{oid}"
    if any(ch in oid for ch in "/%~"):
        name = base64.urlsafe_b64encode(name.encode()).decode().rstrip("=")
    try:
        r = requests.delete(f"{API}/accounts/{account}/productInputs/{name}", timeout=TIMEOUT,
                            params={"dataSource": f"accounts/{account}/dataSources/{source}"},
                            headers={"Authorization": f"Bearer {token}"})
    except requests.RequestException as exc:
        return False, f"Could not reach Google: {exc.__class__.__name__}"
    if r.status_code in (200, 404):
        _status(product, oid, "removed", "Removed from Merchant Center.")
        return True, "Removed"
    msg = (HINTS.get(r.status_code, "") + " " + _error_text(r)).strip()
    _status(product, oid, "error", msg)
    return False, msg


def sync_product(product_id):
    """Send or remove one product depending on whether it is public. Used by the save signal."""
    from products.models import Product
    s = SeoSettings.get()
    if not s.merchant_api_enabled:
        return None
    product = Product.objects.filter(pk=product_id).first()
    if not product:
        return None
    if seo.public_products().filter(pk=product_id).exists() and not s.hide_from_search_engines:
        return upsert(product, s)
    if MerchantProduct.objects.filter(product=product).exclude(status="removed").exists():
        return delete(product, s)
    return None


def sync_all(user=None):
    """Send every public product (admin button). Logged in IndexingLog (engine 'merchant')."""
    s = SeoSettings.get()
    qs = seo.public_products().select_related("brand").prefetch_related("images", "category")
    sent, failed, errors = 0, 0, []
    for p in qs.iterator(chunk_size=100):
        ok, msg = upsert(p, s)
        if ok:
            sent += 1
        else:
            failed += 1
            errors.append(f"{offer_id(p)}: {msg}")
            if "Permission denied" in msg or "refused" in msg or "first" in msg:
                break  # configuration problem: every product would fail the same way
    text = f"{sent} product(s) sent, {failed} failed." + (" " + " | ".join(errors[:5]) if errors else "")
    _record("merchant", [], failed == 0, None, text, action="sync_all", user=user)
    return sent, failed, text


def test_connection():
    """Lists one product of the data source's account to prove the key + account ID work."""
    s = SeoSettings.get()
    account, _, token = _config(s)
    try:
        r = requests.get(f"{API}/accounts/{account}/products", params={"pageSize": 1}, timeout=TIMEOUT,
                         headers={"Authorization": f"Bearer {token}"})
    except requests.RequestException as exc:
        raise MerchantError(f"Could not reach Google: {exc.__class__.__name__}")
    if r.status_code != 200:
        raise MerchantError((HINTS.get(r.status_code, "") + " " + _error_text(r)).strip())
    return f"Connected to Merchant Center account {account}."
