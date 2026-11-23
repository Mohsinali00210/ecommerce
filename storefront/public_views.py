"""Public SEO endpoints: robots.txt, IndexNow key file, Google Merchant Center feed."""
from decimal import Decimal
from xml.sax.saxutils import escape

from django.http import Http404, HttpResponse
from django.views.decorators.cache import cache_page
from django.views.decorators.http import require_GET

from . import seo
from .models import SeoSettings

ROBOTS_DISALLOW = ["/Adminpanel/", "/admin/", "/accounts/", "/api/", "/api/v1/", "/chat/", "/couriers/",
                   "/payments/", "/order/view/", "/MyCart/", "/CheckoutPage/", "/Orders/", "/orderdetail/",
                   "/Wishlist/", "/user-profile/", "/edit-profile/", "/change-password/", "/user-wallet/",
                   "/user-address/", "/notifications/", "/all-notifications/", "/contact/history/",
                   "/contact/ticket/", "/wallet/", "/header-counts/", "/*?*sort=", "/*?*min_price=",
                   "/*?*max_price="]


@require_GET
def robots_txt(request):
    s = SeoSettings.get()
    lines = ["User-agent: *"]
    if s.hide_from_search_engines:
        lines.append("Disallow: /")
    else:
        lines += [f"Disallow: {p}" for p in ROBOTS_DISALLOW]
        lines.append("Allow: /")
    if s.robots_extra.strip():
        lines += ["", s.robots_extra.strip()]
    lines += ["", f"Sitemap: {seo.site_url()}/sitemap.xml", ""]
    return HttpResponse("\n".join(lines), content_type="text/plain; charset=utf-8")


@require_GET
def sitemap_index(request):
    """Sitemap index that always lists SITE_URL links (Django's own uses the request host)."""
    from django.urls import reverse

    from .sitemaps import SITEMAPS
    parts = []
    for section, cls in SITEMAPS.items():
        sm = cls()
        loc = seo.site_url() + reverse("storefront_sitemap_section", kwargs={"section": section})
        pages = max(sm.paginator.num_pages, 1)
        for page in range(1, pages + 1):
            url = loc if page == 1 else f"{loc}?p={page}"
            parts.append(f"<sitemap><loc>{escape(url)}</loc></sitemap>")
    xml = ('<?xml version="1.0" encoding="UTF-8"?>\n'
           '<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">' + "".join(parts) + "</sitemapindex>")
    return HttpResponse(xml, content_type="application/xml; charset=utf-8")


@require_GET
def indexnow_key(request, key):
    s = SeoSettings.get()
    if not s.indexnow_key or key != s.indexnow_key:
        raise Http404
    return HttpResponse(s.indexnow_key, content_type="text/plain; charset=utf-8")


def _money(v):
    return f"{Decimal(v):.2f} PKR"


def _tag(name, value):
    return f"<{name}>{escape(str(value))}</{name}>" if value not in (None, "") else ""


@require_GET
@cache_page(60 * 30)
def google_merchant_feed(request):
    """RSS 2.0 product feed for Google Merchant Center (free listings + Shopping ads)."""
    s = SeoSettings.get()
    if not s.merchant_feed_enabled:
        raise Http404
    from adminpanel import shipping
    rules = shipping.rules()
    items = []
    qs = seo.public_products().select_related("brand").prefetch_related("images", "category")
    for p in qs.iterator(chunk_size=200):
        images = seo.product_images(p, limit=11)
        if not images:
            continue  # Google rejects items without an image
        final, was = seo.product_price(p)
        link = seo.product_url(p)
        cats = [c for c in p.category.all() if not c.is_deleted]
        ship = Decimal("0") if (p.free_shipping or (rules["free_enabled"] and final >= rules["free_threshold"])) \
            else (p.shipping_charges or Decimal("0")) + (p.additional_shipping_charges or Decimal("0"))
        if rules["max_shipping"] is not None:
            ship = min(ship, rules["max_shipping"])
        availability = "preorder" if getattr(p, "available_for_preorder", False) else (
            "in_stock" if seo.in_stock(p) else "out_of_stock")
        brand = getattr(p.brand, "name", "") or s.merchant_default_brand or s.site_name
        parts = [
            _tag("g:id", p.sku or p.pk), _tag("g:title", (p.name or "")[:150]),
            _tag("g:description", seo.clean_text(p.description or p.brief_description or p.name, 5000)),
            _tag("g:link", link), _tag("g:image_link", images[0]),
            *[_tag("g:additional_image_link", u) for u in images[1:11]],
            _tag("g:availability", availability), _tag("g:condition", "new"),
            _tag("g:price", _money(was if was else final)),
            _tag("g:sale_price", _money(final) if was else ""),
            _tag("g:brand", brand), _tag("g:identifier_exists", "no"), _tag("g:mpn", p.sku),
            _tag("g:product_type", " > ".join(c.name for c in cats[:3])),
            _tag("g:google_product_category", s.merchant_google_category),
            f"<g:shipping>{_tag('g:country', s.country or 'PK')}{_tag('g:price', _money(ship))}</g:shipping>",
        ]
        if p.weight and p.weight > 0:
            parts.append(_tag("g:shipping_weight", f"{p.weight} kg"))
        items.append("<item>" + "".join(x for x in parts if x) + "</item>")
    xml = ('<?xml version="1.0" encoding="UTF-8"?>\n'
           '<rss version="2.0" xmlns:g="http://base.google.com/ns/1.0"><channel>'
           f"{_tag('title', s.site_name)}{_tag('link', seo.site_url() + '/')}"
           f"{_tag('description', s.default_description)}" + "".join(items) + "</channel></rss>")
    return HttpResponse(xml, content_type="application/xml; charset=utf-8")
