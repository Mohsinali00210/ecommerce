"""Builds the <head> SEO data for every storefront page.

`page_meta(context)` looks at the page being rendered (URL name + the objects the
view put in the template context) and returns title, description, canonical URL,
robots, Open Graph / Twitter values and JSON-LD structured data.
No view has to change: products, blog posts, categories and the home page are
recognised automatically, everything else gets sensible defaults.
"""
import json
from decimal import Decimal

from django.conf import settings
from django.urls import NoReverseMatch, reverse
from django.utils.html import strip_tags
from django.utils.text import Truncator

from .models import SeoSettings

# Pages that must never appear in search results.
PRIVATE_URL_NAMES = {
    "MyCheckoutPage", "MyCart", "Orders", "order-detail", "Wishlist", "user-profile", "edit-profile",
    "change-password", "user-wallet", "user-address", "ContactHistory", "TicketDetail", "notifications",
    "all-notifications", "user-withdraw", "wish-to-buy",
}
PRIVATE_PREFIXES = ("/Adminpanel/", "/admin/", "/accounts/", "/order/view/", "/payments/", "/couriers/",
                    "/api/", "/chat/")


def site_url():
    """Public address of the shop: SEO settings > Public site address, else SITE_URL."""
    try:
        addr = SeoSettings.get().site_address
    except Exception:  # table not migrated yet
        addr = ""
    return (addr or getattr(settings, "SITE_URL", "") or "").rstrip("/")


def absolute(url):
    if not url:
        return ""
    if url.startswith(("http://", "https://")):
        return url
    if url.startswith("//"):
        return "https:" + url
    return site_url() + (url if url.startswith("/") else "/" + url)


def media_url(field):
    try:
        return absolute(field.url) if field else ""
    except ValueError:
        return ""


def clean_text(value, length=160):
    text = " ".join(strip_tags(value or "").split())
    return Truncator(text).chars(length, truncate="…")


# ---------------------------------------------------------------------------
# Public catalogue queries (also used by the sitemap, feed and IndexNow)
# ---------------------------------------------------------------------------
def public_products():
    from products.models import Product
    return (Product.objects.filter(is_deleted=False, is_active=True, status__in=["active", "featured"],
                                   visible_individually=True)
            .exclude(slug=""))


def public_categories():
    from products.models import Category
    return Category.objects.filter(is_deleted=False, is_active=True)


def public_posts():
    from UserPanel.models import BlogPost
    return BlogPost.objects.filter(status="published", is_deleted=False).exclude(slug="")


def product_url(product):
    return absolute(reverse("home:Product_Details", args=[product.slug]))


def category_url(category):
    return absolute(reverse("home:search-products") + f"?category={category.pk}")


def post_url(post):
    return absolute(reverse("home:blog-detail", args=[post.slug]))


def product_price(product):
    """Price after any running promotion (same rules as the product page)."""
    try:
        from django.utils import timezone

        from UserPanel.views import build_pricing, get_active_promotion
        promo = get_active_promotion(product, timezone.now())
        p = build_pricing(product.price, promo)
        return Decimal(p["final"]), (Decimal(p["was"]) if p.get("was") else None)
    except Exception:  # pricing helpers changed: fall back to the list price
        return Decimal(product.price or 0), None


def product_images(product, limit=10):
    imgs = []
    try:
        for im in product.images.all():
            if getattr(im, "is_deleted", False):
                continue
            u = media_url(im.image)
            if u:
                imgs.append(u)
            if len(imgs) >= limit:
                break
    except Exception:
        pass
    return imgs


def in_stock(product):
    if getattr(product, "available_for_preorder", False):
        return True
    return product.stock_status != "out_of_stock" and (product.stock_quantity or 0) > 0


# ---------------------------------------------------------------------------
# JSON-LD builders
# ---------------------------------------------------------------------------
def organization_ld(seo):
    org = {"@type": "OnlineStore", "@id": site_url() + "/#organization", "name": seo.site_name,
           "url": site_url() + "/"}
    if seo.logo:
        org["logo"] = media_url(seo.logo)
    if seo.phone or seo.email:
        cp = {"@type": "ContactPoint", "contactType": "customer support"}
        if seo.phone:
            cp["telephone"] = seo.phone
        if seo.email:
            cp["email"] = seo.email
        org["contactPoint"] = cp
    if seo.street_address or seo.city:
        org["address"] = {k: v for k, v in {
            "@type": "PostalAddress", "streetAddress": seo.street_address, "addressLocality": seo.city,
            "addressRegion": seo.region, "postalCode": seo.postal_code, "addressCountry": seo.country,
        }.items() if v}
    if seo.social_list():
        org["sameAs"] = seo.social_list()
    return org


def website_ld(seo):
    return {
        "@type": "WebSite", "@id": site_url() + "/#website", "name": seo.site_name, "url": site_url() + "/",
        "publisher": {"@id": site_url() + "/#organization"},
        "potentialAction": {
            "@type": "SearchAction",
            "target": {"@type": "EntryPoint",
                       "urlTemplate": absolute(reverse("home:search-products")) + "?q={search_term_string}"},
            "query-input": "required name=search_term_string",
        },
    }


def breadcrumb_ld(items):
    return {"@type": "BreadcrumbList", "itemListElement": [
        {"@type": "ListItem", "position": i, "name": name, "item": url}
        for i, (name, url) in enumerate(items, 1)]}


def product_ld(product, seo, price, url, images, reviews=None):
    from adminpanel import shipping
    rules = shipping.rules()
    brand = getattr(getattr(product, "brand", None), "name", "") or seo.merchant_default_brand or seo.site_name
    offer = {
        "@type": "Offer", "url": url, "priceCurrency": "PKR", "price": f"{price:.2f}",
        "availability": "https://schema.org/" + ("InStock" if in_stock(product) else "OutOfStock"),
        "itemCondition": "https://schema.org/NewCondition",
        "seller": {"@id": site_url() + "/#organization"},
    }
    if getattr(product, "available_for_preorder", False):
        offer["availability"] = "https://schema.org/PreOrder"
    ship_cost = Decimal("0") if (product.free_shipping or (rules["free_enabled"] and price >= rules["free_threshold"])) \
        else (product.shipping_charges or Decimal("0")) + (product.additional_shipping_charges or Decimal("0"))
    offer["shippingDetails"] = {
        "@type": "OfferShippingDetails",
        "shippingRate": {"@type": "MonetaryAmount", "value": f"{ship_cost:.2f}", "currency": "PKR"},
        "shippingDestination": {"@type": "DefinedRegion", "addressCountry": seo.country or "PK"},
        "deliveryTime": {
            "@type": "ShippingDeliveryTime",
            "handlingTime": {"@type": "QuantitativeValue", "minValue": 0,
                             "maxValue": max(int(product.handling_time or 1), 0), "unitCode": "DAY"},
            "transitTime": {"@type": "QuantitativeValue", "minValue": 1, "maxValue": 5, "unitCode": "DAY"},
        },
    }
    if seo.return_days:
        offer["hasMerchantReturnPolicy"] = {
            "@type": "MerchantReturnPolicy", "applicableCountry": seo.country or "PK",
            "returnPolicyCategory": "https://schema.org/MerchantReturnFiniteReturnWindow",
            "merchantReturnDays": seo.return_days, "returnMethod": "https://schema.org/ReturnByMail",
            "returnFees": "https://schema.org/FreeReturn",
        }
    data = {
        "@type": "Product", "@id": url + "#product", "name": product.name, "url": url, "sku": product.sku,
        "description": clean_text(product.description or product.brief_description, 500),
        "brand": {"@type": "Brand", "name": brand}, "offers": offer,
    }
    if images:
        data["image"] = images
    category = product.category.filter(is_deleted=False).first() if hasattr(product, "category") else None
    if category:
        data["category"] = category.name
    if reviews is not None:
        rated = [r.rating for r in reviews if getattr(r, "rating", None)]
        if rated:
            data["aggregateRating"] = {"@type": "AggregateRating",
                                       "ratingValue": round(sum(rated) / len(rated), 1),
                                       "reviewCount": len(rated)}
    return data


def blog_ld(post, seo, url, image):
    data = {
        "@type": "BlogPosting", "headline": post.title[:110], "url": url, "mainEntityOfPage": url,
        "description": clean_text(post.meta_description or post.excerpt or post.content),
        "publisher": {"@id": site_url() + "/#organization"},
    }
    if image:
        data["image"] = [image]
    if post.published_at:
        data["datePublished"] = post.published_at.isoformat()
    if getattr(post, "modified_at", None):
        data["dateModified"] = post.modified_at.isoformat()
    if post.author:
        data["author"] = {"@type": "Person", "name": post.author.get_full_name() or seo.site_name}
    return data


# ---------------------------------------------------------------------------
# Page meta
# ---------------------------------------------------------------------------
def _title(seo, text):
    return f"{text}{seo.title_suffix}" if text else seo.home_title


def page_meta(context):
    request = context.get("request")
    seo = SeoSettings.get()
    match = getattr(request, "resolver_match", None)
    name = getattr(match, "url_name", "") or ""
    path = getattr(request, "path", "/") or "/"
    home_url = absolute(reverse("home:home"))

    meta = {
        "title": seo.home_title, "description": seo.default_description,
        "canonical": absolute(path), "robots": "index, follow, max-image-preview:large",
        "og_type": "website", "image": media_url(seo.default_share_image), "site_name": seo.site_name,
        "twitter": seo.twitter_handle, "ld": [], "price": None,
    }
    graph = [organization_ld(seo), website_ld(seo)] if name == "home" else []

    product = context.get("product")
    post = context.get("post")

    if name == "Product_Details" and product is not None:
        url = product_url(product)
        price, _ = product_price(product)
        images = product_images(product)
        meta.update(
            title=product.meta_title or _title(seo, product.name),
            description=clean_text(product.meta_description or product.brief_description
                                   or product.description) or seo.default_description,
            canonical=url, og_type="product", image=images[0] if images else meta["image"],
            price=price, availability="in stock" if in_stock(product) else "out of stock",
        )
        reviews = context.get("Reviews")
        try:
            reviews = list(reviews) if reviews is not None else None
        except TypeError:
            reviews = None
        crumbs = [("Home", home_url)]
        cat = product.category.filter(is_deleted=False).first()
        if cat:
            crumbs.append((cat.name, category_url(cat)))
        crumbs.append((product.name, url))
        graph += [product_ld(product, seo, price, url, images, reviews), breadcrumb_ld(crumbs)]

    elif name == "blog-detail" and post is not None:
        url = post_url(post)
        image = media_url(post.featured_image)
        meta.update(title=post.meta_title or _title(seo, post.title),
                    description=clean_text(post.meta_description or post.excerpt or post.content)
                    or seo.default_description,
                    canonical=url, og_type="article", image=image or meta["image"])
        graph += [blog_ld(post, seo, url, image),
                  breadcrumb_ld([("Home", home_url), ("Blog", absolute(reverse("home:blog"))), (post.title, url)])]

    elif name == "search-products":
        q = request.GET
        cats = [c for c in q.getlist("category") if c]
        other_filters = any(k for k in q.keys() if k not in ("category", "page"))
        if len(cats) == 1 and not other_filters and cats[0].isdigit():
            cat = public_categories().filter(pk=int(cats[0])).first()
            if cat:
                meta.update(title=_title(seo, f"{cat.name} — Shop Online in Pakistan"),
                            description=clean_text(f"Shop {cat.name} at {seo.site_name}. "
                                                   f"{seo.default_description}"),
                            canonical=category_url(cat), image=media_url(cat.image) or meta["image"])
                graph.append(breadcrumb_ld([("Home", home_url), (cat.name, category_url(cat))]))
            else:
                meta["robots"] = "noindex, follow"
        elif not q:
            meta.update(title=_title(seo, "Shop All Products"), canonical=absolute(path))
        else:
            # filtered / keyword searches: let crawlers follow links but keep them out of results
            meta.update(title=_title(seo, f"Search: {q.get('q')}" if q.get("q") else "Search"),
                        robots="noindex, follow", canonical=absolute(path))

    elif name == "home":
        meta["canonical"] = home_url
    else:
        page_titles = {"best-deals": "Best Deals", "blog": "Blog", "Contact": "Contact Us",
                       "track-order": "Track Your Order"}
        if name in page_titles:
            meta["title"] = _title(seo, page_titles[name])
        elif context.get("title"):
            meta["title"] = _title(seo, str(context.get("title")))

    if name in PRIVATE_URL_NAMES or path.startswith(PRIVATE_PREFIXES):
        meta["robots"] = "noindex, nofollow"
    if seo.hide_from_search_engines:
        meta["robots"] = "noindex, nofollow"
    if not meta["image"] and seo.logo:
        meta["image"] = media_url(seo.logo)

    if graph:
        meta["ld"] = json.dumps({"@context": "https://schema.org", "@graph": graph},
                                ensure_ascii=False, default=str).replace("</", "<\\/")
    meta["google_verification"] = seo.google_site_verification
    meta["bing_verification"] = seo.bing_site_verification
    meta["ga4"] = seo.google_analytics_id
    return meta


def safe_reverse(name, *args):
    try:
        return reverse(name, args=args)
    except NoReverseMatch:
        return ""
