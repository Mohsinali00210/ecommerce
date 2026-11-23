"""XML sitemaps: /sitemap.xml (index) -> pages, products, categories, blog."""
from urllib.parse import urlsplit

from django.contrib.sitemaps import Sitemap
from django.urls import reverse

from . import seo


class _Base(Sitemap):
    limit = 5000

    @property
    def protocol(self):
        return urlsplit(seo.site_url()).scheme or "https"

    def get_domain(self, site=None):
        # Always the public domain from SITE_URL, never the host the request came in on.
        return urlsplit(seo.site_url()).netloc or super().get_domain(site)


# Built-in public pages: key -> (URL name, label, priority, changefreq)
BUILTIN_PAGES = {
    "home": ("home:home", "Home page", 1.0, "daily"),
    "shop": ("home:search-products", "Shop / all products", 0.8, "daily"),
    "deals": ("home:best-deals", "Best deals", 0.8, "daily"),
    "blog": ("home:blog", "Blog", 0.6, "weekly"),
    "contact": ("home:Contact", "Contact us", 0.5, "monthly"),
    "track": ("home:track-order", "Track your order", 0.4, "monthly"),
}
CHANGEFREQS = ("always", "hourly", "daily", "weekly", "monthly", "yearly", "never")


def parse_extra_pages(text):
    """'/path/ | 0.8 | weekly' lines -> [(path, priority, changefreq)]. Raises ValueError on a bad line."""
    from urllib.parse import urlsplit
    out, host = [], urlsplit(seo.site_url()).netloc
    for n, raw in enumerate((text or "").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = [p.strip() for p in line.split("|")]
        url = parts[0]
        if url.startswith(("http://", "https://")):
            u = urlsplit(url)
            if u.netloc != host:
                raise ValueError(f"Line {n}: only pages of {seo.site_url()} can be listed.")
            url = (u.path or "/") + (f"?{u.query}" if u.query else "")
        if not url.startswith("/") or any(c in url for c in ' <>"\''):
            raise ValueError(f"Line {n}: start with / (e.g. /about-us/) or a full https:// link.")
        if url.startswith(seo.PRIVATE_PREFIXES):
            raise ValueError(f"Line {n}: {url} is a private page and can't be in the sitemap.")
        priority, freq = 0.5, "weekly"
        if len(parts) > 1 and parts[1]:
            try:
                priority = float(parts[1])
            except ValueError:
                raise ValueError(f"Line {n}: priority must be a number from 0.0 to 1.0.")
            if not 0 <= priority <= 1:
                raise ValueError(f"Line {n}: priority must be from 0.0 to 1.0.")
        if len(parts) > 2 and parts[2]:
            freq = parts[2].lower()
            if freq not in CHANGEFREQS:
                raise ValueError(f"Line {n}: how often must be one of {', '.join(CHANGEFREQS)}.")
        out.append((url, priority, freq))
    return out


def page_entries():
    """Everything sitemap-pages.xml lists: [(path, priority, changefreq, label)]."""
    from .models import SeoSettings
    s = SeoSettings.get()
    chosen = s.sitemap_builtin_pages or list(BUILTIN_PAGES)
    entries, seen = [], set()
    for key in BUILTIN_PAGES:
        if key in chosen:
            name, label, prio, freq = BUILTIN_PAGES[key]
            path = reverse(name)
            entries.append((path, prio, freq, label))
            seen.add(path)
    try:
        extra = parse_extra_pages(s.sitemap_extra_pages)
    except ValueError:
        extra = []
    for path, prio, freq in extra:
        if path not in seen:
            entries.append((path, prio, freq, "Custom page"))
            seen.add(path)
    return entries


class StaticSitemap(_Base):
    def items(self):
        return page_entries()

    def location(self, item):
        return item[0]

    def priority(self, item):
        return item[1]

    def changefreq(self, item):
        return item[2]


class ProductSitemap(_Base):
    changefreq = "weekly"
    priority = 0.9

    def items(self):
        return seo.public_products().order_by("-modified_at")

    def location(self, obj):
        return reverse("home:Product_Details", args=[obj.slug])

    def lastmod(self, obj):
        return obj.modified_at


class CategorySitemap(_Base):
    changefreq = "weekly"
    priority = 0.7

    def items(self):
        return seo.public_categories().order_by("pk")

    def location(self, obj):
        return reverse("home:search-products") + f"?category={obj.pk}"


class BlogSitemap(_Base):
    changefreq = "monthly"
    priority = 0.5

    def items(self):
        return seo.public_posts().order_by("-published_at")

    def location(self, obj):
        return reverse("home:blog-detail", args=[obj.slug])

    def lastmod(self, obj):
        return obj.modified_at


SITEMAPS = {"pages": StaticSitemap, "products": ProductSitemap, "categories": CategorySitemap,
            "blog": BlogSitemap}
