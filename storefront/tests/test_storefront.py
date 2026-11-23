"""Storefront: home features, free-shipping rules, SEO tags, sitemap, robots, feed, IndexNow,
Google Indexing API, admin pages, and the editable courier webhook URL."""
import json
import re
from decimal import Decimal
from unittest import mock

from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, override_settings
from django.urls import reverse

from accounts.models import User
from adminpanel import shipping
from adminpanel.models import StoreSettings
from payments.tests.test_orders_payments import TMP, Base, png_bytes
from products.models import ProductImage
from storefront import indexing
from storefront.models import HomeFeature, IndexingLog, SeoSettings
from Web.models import Order


def ld_of(html):
    m = re.search(r'<script type="application/ld\+json">(.*?)</script>', html, re.S)
    return json.loads(m.group(1)) if m else None


def types_in(ld):
    return [g["@type"] for g in ld["@graph"]] if ld else []


class ShopBase(Base):
    def setUp(self):
        super().setUp()
        # queryset update: Product.save() would re-sync (and deactivate) the fixture's variant
        from products.models import Product
        Product.objects.filter(pk=self.product.pk).update(
            slug="lawn-suit", shipping_charges=Decimal("200"),
            description="<p>Soft <b>printed</b> lawn, 3 pieces.</p>")
        self.product.refresh_from_db()
        SeoSettings.objects.update_or_create(pk=1, defaults={"site_address": ""})  # tests use SITE_URL
        cache.clear()
        self.product.category.set([self.cat])
        self.store.free_shipping_enabled = True
        self.store.free_shipping_threshold = Decimal("3500")
        self.store.max_shipping_charge = Decimal("450")
        self.store.save()

    def add_image(self, product=None):
        f = SimpleUploadedFile("p.png", png_bytes(), content_type="image/png")
        return ProductImage.objects.create(product=product or self.product, image=f)

    def staff(self, *roles):
        from django.contrib.auth.models import Group

        from accounts.rbac import sync_roles
        sync_roles()
        u = User.objects.create_user(email=f"{'-'.join(roles) or 'none'}@x.com", password="Pw-Strong-123",
                                     full_name="Staff", is_staff=True)
        for r in roles:
            u.groups.add(Group.objects.get(name=r))
        c = Client()
        c.force_login(u)
        return c

    def admin(self):
        c = Client()
        c.force_login(self.root)
        return c


# ---------------------------------------------------------------------------
# Free shipping rules
# ---------------------------------------------------------------------------
class ShippingRuleTests(ShopBase):
    def test_below_threshold_pays_capped_shipping(self):
        t = shipping.totals(Decimal("3000"), Decimal("0"), Decimal("600"))
        self.assertEqual(t["shipping_total"], Decimal("450"))
        self.assertTrue(t["shipping_capped"])
        self.assertFalse(t["free_shipping_applied"])
        self.assertEqual(t["final_total"], Decimal("3450"))

    def test_threshold_uses_amount_after_discounts(self):
        t = shipping.totals(Decimal("3600"), Decimal("200"), Decimal("200"))  # goods = 3400 < 3500
        self.assertEqual(t["shipping_total"], Decimal("200"))
        t = shipping.totals(Decimal("3700"), Decimal("200"), Decimal("200"))  # goods = 3500
        self.assertEqual(t["shipping_total"], Decimal("0"))
        self.assertTrue(t["free_shipping_applied"])
        self.assertEqual(t["final_total"], Decimal("3500"))

    def test_disabled_and_no_cap(self):
        self.store.free_shipping_enabled = False
        self.store.max_shipping_charge = Decimal("0")
        self.store.save()
        t = shipping.totals(Decimal("9000"), Decimal("0"), Decimal("900"))
        self.assertEqual(t["shipping_total"], Decimal("900"))
        self.assertIsNone(t["max_shipping"])
        self.assertIsNone(t["free_shipping_threshold"])

    def test_order_placement_applies_free_shipping(self):
        r = self.checkout(self.cust_client(), qty=2)  # 2 x 2500 = 5000 >= 3500
        self.assertEqual(r.status_code, 201, r.content)
        order = Order.objects.get()
        self.assertEqual(order.shipping_charges, Decimal("0"))
        self.assertEqual(order.total_amount, Decimal("5000"))

    def test_order_placement_charges_below_threshold(self):
        r = self.checkout(self.cust_client(), qty=1)  # 2500 < 3500
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(Order.objects.get().shipping_charges, Decimal("200"))

    def test_product_note_kinds(self):
        self.assertEqual(shipping.product_note(self.product, Decimal("2500"))["kind"], "add_more")
        self.assertEqual(shipping.product_note(self.product, Decimal("2500"))["remaining"], Decimal("1000"))
        self.assertEqual(shipping.product_note(self.product, Decimal("4000"))["kind"], "free_threshold")
        self.product.free_shipping = True
        self.assertEqual(shipping.product_note(self.product, Decimal("10"))["kind"], "free_item")

    def test_product_page_and_quick_view_show_criteria(self):
        page = Client().get(reverse("home:Product_Details", args=["lawn-suit"]))
        self.assertContains(page, "Free shipping on orders over")
        self.assertContains(page, "RS 3,500")
        self.assertContains(page, "RS 1,000")  # remaining
        qv = Client().get(reverse("home:product_quick_view", args=[self.product.pk]))
        self.assertContains(qv, "Free shipping on orders over")
        self.assertContains(qv, 'id="qvPriceNow"')

    def test_store_settings_page_saves_shipping(self):
        c = self.admin()
        r = c.get(reverse("admin_store_settings"))
        self.assertContains(r, "Free shipping from")
        data = {k: v for k, v in {
            "cod_enabled": "on", "online_payment_timeout_minutes": 60, "free_shipping_enabled": "on",
            "free_shipping_threshold": "5000", "max_shipping_charge": "300", "backup_hour": 3, "backup_keep": 7,
        }.items()}
        r = c.post(reverse("admin_store_settings"), data)
        self.assertEqual(r.status_code, 302, getattr(r, "context", None) and r.context["form"].errors)
        s = StoreSettings.objects.get()
        self.assertEqual((s.free_shipping_threshold, s.max_shipping_charge), (Decimal("5000"), Decimal("300")))
        r = c.post(reverse("admin_store_settings"), {**data, "free_shipping_threshold": "-1"})
        self.assertEqual(r.status_code, 200)


# ---------------------------------------------------------------------------
# Home page features
# ---------------------------------------------------------------------------
class HomeFeatureTests(ShopBase):
    def test_seeded_tiles_render_with_threshold(self):
        self.assertEqual(HomeFeature.objects.count(), 4)
        r = Client().get("/")
        self.assertContains(r, "Free Shipping")
        self.assertContains(r, "On orders over PKR 3,500")
        self.assertContains(r, "Cash on Delivery")

    def test_admin_edits_tiles(self):
        c = self.admin()
        page = c.get(reverse("storefront_home_features"))
        self.assertEqual(page.status_code, 200)
        rows = list(HomeFeature.objects.all())
        data = {"form-TOTAL_FORMS": len(rows) + 1, "form-INITIAL_FORMS": len(rows),
                "form-MIN_NUM_FORMS": 0, "form-MAX_NUM_FORMS": 1000}
        for i, f in enumerate(rows):
            data.update({f"form-{i}-id": f.pk, f"form-{i}-icon": f.icon, f"form-{i}-title": f.title,
                         f"form-{i}-subtitle": f.subtitle, f"form-{i}-link_url": "",
                         f"form-{i}-sort_order": f.sort_order, f"form-{i}-is_active": "on"})
        data["form-0-title"] = "Free Delivery"
        data["form-3-DELETE"] = "on"
        n = len(rows)
        data.update({f"form-{n}-icon": "headset", f"form-{n}-title": "24/7 Support",
                     f"form-{n}-subtitle": "WhatsApp us", f"form-{n}-link_url": "/Contact/",
                     f"form-{n}-sort_order": 99, f"form-{n}-is_active": "on"})
        r = c.post(reverse("storefront_home_features"), data)
        self.assertEqual(r.status_code, 302)
        titles = list(HomeFeature.objects.values_list("title", flat=True))
        self.assertEqual(titles, ["Free Delivery", "Cash on Delivery", "7 Days Returns", "24/7 Support"])
        self.assertEqual(HomeFeature.objects.get(title="24/7 Support").icon, "bi-headset")
        home = Client().get("/")
        self.assertContains(home, "24/7 Support")
        self.assertContains(home, 'href="/Contact/"')
        self.assertNotContains(home, "100% Secure Payment")

    def test_bad_link_is_rejected(self):
        f = HomeFeature.objects.first()
        data = {"form-TOTAL_FORMS": 1, "form-INITIAL_FORMS": 1, "form-MIN_NUM_FORMS": 0,
                "form-MAX_NUM_FORMS": 1000, "form-0-id": f.pk, "form-0-icon": "bi-truck", "form-0-title": "X",
                "form-0-subtitle": "", "form-0-link_url": "javascript:alert(1)", "form-0-sort_order": 1,
                "form-0-is_active": "on"}
        r = self.admin().post(reverse("storefront_home_features"), data)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(HomeFeature.objects.get(pk=f.pk).link_url, "")

    def test_hidden_when_no_tiles(self):
        HomeFeature.objects.update(is_active=False)
        cache.clear()
        self.assertNotContains(Client().get("/"), 'class="trust-row"')

    def test_rbac(self):
        self.assertEqual(self.staff("Support Agent").post(reverse("storefront_home_features"), {}).status_code, 403)
        self.assertEqual(self.staff("Analyst").get(reverse("storefront_seo")).status_code, 403)
        self.assertEqual(self.staff("Catalog Manager").get(reverse("storefront_seo")).status_code, 200)
        self.assertEqual(self.cust_client().get(reverse("storefront_home_features")).status_code, 403)


# ---------------------------------------------------------------------------
# SEO tags
# ---------------------------------------------------------------------------
class SeoTagTests(ShopBase):
    def test_home_has_title_canonical_and_website_ld(self):
        html = Client().get("/").content.decode()
        self.assertIn("<title>Shan Zee — Considered Goods, Well Made</title>", html)
        self.assertIn('<link rel="canonical" href="https://shop.test/">', html)
        self.assertIn('property="og:type" content="website"', html)
        self.assertEqual(set(types_in(ld_of(html))), {"OnlineStore", "WebSite"})
        self.assertEqual(html.count("<title>"), 1)

    def test_product_page(self):
        self.add_image()
        html = Client().get(reverse("home:Product_Details", args=["lawn-suit"])).content.decode()
        self.assertIn("<title>Lawn Suit — Shan Zee</title>", html)
        self.assertIn('<link rel="canonical" href="https://shop.test/product/lawn-suit/">', html)
        self.assertIn('content="Soft printed lawn, 3 pieces."', html)
        self.assertIn('property="og:type" content="product"', html)
        self.assertIn('property="product:price:amount" content="2500.00"', html)
        self.assertRegex(html, r'property="og:image" content="https://shop\.test/media/products/')
        ld = ld_of(html)
        product = next(g for g in ld["@graph"] if g["@type"] == "Product")
        self.assertEqual(product["offers"]["price"], "2500.00")
        self.assertEqual(product["offers"]["priceCurrency"], "PKR")
        self.assertEqual(product["offers"]["availability"], "https://schema.org/InStock")
        self.assertEqual(product["offers"]["shippingDetails"]["shippingRate"]["value"], "200.00")
        self.assertIn("BreadcrumbList", types_in(ld))

    def test_meta_title_override_and_variant_url_canonical(self):
        self.product.meta_title = "Buy Lawn Suit Online"
        self.product.save()
        html = Client().get(reverse("home:Product_Details", args=["lawn-suit", "LS-M"])).content.decode()
        self.assertIn("<title>Buy Lawn Suit Online</title>", html)
        self.assertIn('href="https://shop.test/product/lawn-suit/"', html)  # variant URL points to the product

    def test_search_and_private_pages_are_noindex(self):
        r = Client().get(reverse("home:search-products") + "?q=lawn")
        self.assertContains(r, 'name="robots" content="noindex, follow"')
        r = Client().get(reverse("home:search-products") + f"?category={self.cat.pk}")
        self.assertContains(r, 'name="robots" content="index, follow')
        self.assertContains(r, f'href="https://shop.test/search-products/?category={self.cat.pk}"')
        r = self.cust_client().get(reverse("home:MyCart"))
        self.assertContains(r, 'content="noindex, nofollow"')

    def test_verification_and_ga(self):
        s = SeoSettings.get()
        s.google_site_verification = "abcDEF123456"
        s.bing_site_verification = "1234567890ABCDEF"
        s.google_analytics_id = "G-TEST1234"
        s.save()
        html = Client().get("/").content.decode()
        self.assertIn('<meta name="google-site-verification" content="abcDEF123456">', html)
        self.assertIn('<meta name="msvalidate.01" content="1234567890ABCDEF">', html)
        self.assertIn("gtag/js?id=G-TEST1234", html)

    def test_hidden_site(self):
        s = SeoSettings.get()
        s.hide_from_search_engines = True
        s.save()
        self.assertContains(Client().get("/"), 'content="noindex, nofollow"')
        self.assertIn("Disallow: /\n", Client().get("/robots.txt").content.decode())

    def test_ld_cannot_break_out_of_script(self):
        self.product.name = "Evil </script><script>alert(1)</script>"
        self.product.save()
        html = Client().get(reverse("home:Product_Details", args=["lawn-suit"])).content.decode()
        self.assertNotIn("</script><script>alert(1)", html)


# ---------------------------------------------------------------------------
# Sitemap, robots, IndexNow key, merchant feed
# ---------------------------------------------------------------------------
class PublicEndpointTests(ShopBase):
    def test_sitemap_index_and_sections(self):
        idx = Client().get("/sitemap.xml").content.decode()
        self.assertIn("https://shop.test/sitemap-products.xml", idx)
        prods = Client().get("/sitemap-products.xml").content.decode()
        self.assertIn("<loc>https://shop.test/product/lawn-suit/</loc>", prods)
        cats = Client().get("/sitemap-categories.xml").content.decode()
        self.assertIn(f"https://shop.test/search-products/?category={self.cat.pk}", cats)

    def test_inactive_products_not_in_sitemap(self):
        self.product.status = "inactive"
        self.product.save()
        cache.clear()
        self.assertNotIn("lawn-suit", Client().get("/sitemap-products.xml").content.decode())

    def test_robots(self):
        txt = Client().get("/robots.txt").content.decode()
        self.assertIn("Disallow: /Adminpanel/", txt)
        self.assertIn("Disallow: /CheckoutPage/", txt)
        self.assertIn("Sitemap: https://shop.test/sitemap.xml", txt)

    def test_indexnow_key_file(self):
        key = SeoSettings.get().indexnow_key
        r = Client().get(f"/{key}.txt")
        self.assertEqual((r.status_code, r.content.decode()), (200, key))
        self.assertEqual(Client().get("/wrongkey123.txt").status_code, 404)

    def test_merchant_feed(self):
        self.add_image()
        cache.clear()
        feed = Client().get(reverse("storefront_merchant_feed")).content.decode()
        self.assertIn("<g:id>LS</g:id>", feed)
        self.assertIn("<g:price>2500.00 PKR</g:price>", feed)
        self.assertIn("<g:availability>in_stock</g:availability>", feed)
        self.assertIn("<g:link>https://shop.test/product/lawn-suit/</g:link>", feed)
        self.assertIn("<g:shipping><g:country>PK</g:country><g:price>200.00 PKR</g:price></g:shipping>", feed)
        from xml.dom import minidom
        minidom.parseString(feed.encode())  # well-formed

    def test_feed_skips_products_without_image(self):
        cache.clear()
        self.assertNotIn("<item>", Client().get(reverse("storefront_merchant_feed")).content.decode())


# ---------------------------------------------------------------------------
# Instant indexing
# ---------------------------------------------------------------------------
class FakeResp:
    def __init__(self, code, data=None):
        self.status_code, self._data = code, data or {}
        self.text = json.dumps(self._data)
        self.content = self.text.encode()

    def json(self):
        return self._data


def service_account():
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                            serialization.NoEncryption()).decode()
    return json.dumps({"type": "service_account", "client_email": "idx@proj.iam.gserviceaccount.com",
                       "private_key": pem, "private_key_id": "k1",
                       "token_uri": "https://oauth2.googleapis.com/token"}), key


class IndexingTests(ShopBase):
    def test_indexnow_payload(self):
        s = SeoSettings.get()
        s.indexnow_enabled = True
        s.save()
        with mock.patch("storefront.indexing.requests.post", return_value=FakeResp(200)) as post:
            rec = indexing.indexnow_submit(["https://shop.test/product/lawn-suit/", "https://evil.test/x"])
        payload = post.call_args.kwargs["json"]
        self.assertEqual(payload["host"], "shop.test")
        self.assertEqual(payload["urlList"], ["https://shop.test/product/lawn-suit/"])  # other domains dropped
        self.assertEqual(payload["keyLocation"], f"https://shop.test/{s.indexnow_key}.txt")
        self.assertTrue(rec.ok)

    def test_indexnow_403_explained(self):
        with mock.patch("storefront.indexing.requests.post", return_value=FakeResp(403)):
            rec = indexing.indexnow_submit(["https://shop.test/"], force=True)
        self.assertFalse(rec.ok)
        self.assertIn("Key not valid", rec.message)

    def test_product_save_pings_engines_once(self):
        s = SeoSettings.get()
        s.indexnow_enabled = True
        s.save()
        with mock.patch("storefront.indexing.requests.post", return_value=FakeResp(200)) as post:
            with self.captureOnCommitCallbacks(execute=True):
                self.product.name = "Lawn Suit 2"
                self.product.save()
            with self.captureOnCommitCallbacks(execute=True):
                self.product.save()  # deduped
        self.assertEqual(post.call_count, 1)
        self.assertEqual(post.call_args.kwargs["json"]["urlList"], ["https://shop.test/product/lawn-suit/"])

    def test_nothing_sent_when_off(self):
        with mock.patch("storefront.indexing.requests.post") as post:
            with self.captureOnCommitCallbacks(execute=True):
                self.product.save()
        post.assert_not_called()

    def test_google_indexing_flow(self):
        raw, key = service_account()
        s = SeoSettings.get()
        s.google_indexing_enabled = True
        s.google_service_account = raw
        s.save()
        calls = []

        def fake_post(url, **kw):
            calls.append((url, kw))
            if "oauth2" in url:
                return FakeResp(200, {"access_token": "tok-1", "expires_in": 3600})
            return FakeResp(200, {"urlNotificationMetadata": {}})
        with mock.patch("storefront.indexing.requests.post", side_effect=fake_post):
            rec = indexing.google_submit(["https://shop.test/product/lawn-suit/"])
        self.assertTrue(rec.ok, rec.message)
        assertion = calls[0][1]["data"]["assertion"]
        head, body, sig = assertion.split(".")
        import base64

        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import padding
        pad = lambda x: x + "=" * (-len(x) % 4)  # noqa: E731
        key.public_key().verify(base64.urlsafe_b64decode(pad(sig)), f"{head}.{body}".encode(),
                                padding.PKCS1v15(), hashes.SHA256())  # raises if the JWT signature is wrong
        claims = json.loads(base64.urlsafe_b64decode(pad(body)))
        self.assertEqual(claims["scope"], "https://www.googleapis.com/auth/indexing")
        self.assertEqual(calls[1][1]["json"], {"url": "https://shop.test/product/lawn-suit/", "type": "URL_UPDATED"})
        self.assertEqual(calls[1][1]["headers"]["Authorization"], "Bearer tok-1")

    def test_google_permission_error_is_explained(self):
        raw, _ = service_account()
        s = SeoSettings.get()
        s.google_service_account = raw
        s.save()

        def fake_post(url, **kw):
            return FakeResp(200, {"access_token": "t"}) if "oauth2" in url else FakeResp(403, {"error": {}})
        with mock.patch("storefront.indexing.requests.post", side_effect=fake_post):
            rec = indexing.google_submit(["https://shop.test/"], force=True)
        self.assertFalse(rec.ok)
        self.assertIn("Owner", rec.message)

    def test_bad_service_account(self):
        with self.assertRaises(indexing.IndexingError):
            indexing.parse_service_account('{"type":"user"}')


# ---------------------------------------------------------------------------
# SEO admin page
# ---------------------------------------------------------------------------
class SeoAdminTests(ShopBase):
    def form(self, **over):
        s = SeoSettings.get()
        data = {"site_name": "Shan Zee", "home_title": s.home_title, "title_suffix": s.title_suffix,
                "default_description": s.default_description, "country": "pk", "return_days": 7,
                "indexnow_key": s.indexnow_key, "merchant_feed_enabled": "on",
                "merchant_default_brand": "Shan Zee",
                "sitemap_builtin_pages": ["home", "shop", "deals", "blog", "contact", "track"]}
        data.update(over)
        return data

    def test_page_and_whole_meta_tag_paste(self):
        c = self.admin()
        self.assertContains(c.get(reverse("storefront_seo")), "Checklist")
        r = c.post(reverse("storefront_seo"), self.form(
            google_site_verification='<meta name="google-site-verification" content="Zx9_abc-DEF123" />',
            twitter_handle="shanzee", social_links="https://instagram.com/shanzee"))
        self.assertEqual(r.status_code, 302)
        s = SeoSettings.objects.get()
        self.assertEqual(s.google_site_verification, "Zx9_abc-DEF123")
        self.assertEqual(s.twitter_handle, "@shanzee")
        self.assertEqual(s.country, "PK")

    def test_validation(self):
        r = self.admin().post(reverse("storefront_seo"), self.form(
            google_analytics_id="UA-123", social_links="instagram.com/x", robots_extra="hello world",
            google_indexing_enabled="on"))
        self.assertEqual(r.status_code, 200)
        errors = r.context["form"].errors
        for f in ("google_analytics_id", "social_links", "robots_extra", "google_indexing_enabled"):
            self.assertIn(f, errors)

    def test_service_account_kept_encrypted_and_not_echoed(self):
        raw, _ = service_account()
        c = self.admin()
        r = c.post(reverse("storefront_seo"), self.form(google_service_account=raw, google_indexing_enabled="on"))
        self.assertEqual(r.status_code, 302)
        self.assertEqual(SeoSettings.objects.get().google_service_account, raw)
        page = c.get(reverse("storefront_seo")).content.decode()
        self.assertIn("idx@proj.iam.gserviceaccount.com", page)
        self.assertNotIn("PRIVATE KEY", page)
        c.post(reverse("storefront_seo"), self.form(google_indexing_enabled="on"))  # blank = keep
        self.assertEqual(SeoSettings.objects.get().google_service_account, raw)
        from django.db import connection
        with connection.cursor() as cur:
            cur.execute("SELECT google_service_account FROM storefront_seosettings")
            self.assertTrue(cur.fetchone()[0].startswith("enc$"))

    def test_submit_url_tool_only_own_domain(self):
        c = self.admin()
        with mock.patch("storefront.indexing.requests.post", return_value=FakeResp(202)) as post:
            c.post(reverse("storefront_seo_tool", args=["submit-url"]), {"url": "https://evil.test/a"})
            post.assert_not_called()
            c.post(reverse("storefront_seo_tool", args=["submit-url"]), {"url": "/product/lawn-suit/"})
        self.assertEqual(post.call_count, 1)
        self.assertTrue(IndexingLog.objects.get().ok)


# ---------------------------------------------------------------------------
# Courier webhook URL editing
# ---------------------------------------------------------------------------
class WebhookEditTests(ShopBase):
    def setUp(self):
        super().setUp()
        from couriers.models import CourierCredential, CourierProvider
        self.provider = CourierProvider.objects.get(code="leopards")
        self.cred = CourierCredential.objects.create(provider=self.provider, api_key="k", api_password="p")

    def post(self, **over):
        data = {"label": "Main", "environment": "sandbox", "api_key": "", "api_password": "",
                "account_number": "", "extra": "{}", "extra_secret": "", "is_active": "on"}
        data.update(over)
        return self.admin().post(reverse("couriers:credential_edit", args=[self.provider.pk, self.cred.pk]), data)

    def test_edit_page_shows_full_url(self):
        r = self.admin().get(reverse("couriers:credential_edit", args=[self.provider.pk, self.cred.pk]))
        self.assertContains(r, f"https://shop.test/couriers/webhook/leopards/{self.cred.webhook_token}/")

    def test_custom_token_and_blank_keeps(self):
        old = self.cred.webhook_token
        self.post(webhook_token="")
        self.cred.refresh_from_db()
        self.assertEqual(self.cred.webhook_token, old)
        self.post(webhook_token="my-shop-hook_2026abcd")
        self.cred.refresh_from_db()
        self.assertEqual(self.cred.webhook_token, "my-shop-hook_2026abcd")
        r = Client().post("/couriers/webhook/leopards/my-shop-hook_2026abcd/",
                          data=json.dumps({"cn_number": "X1", "status": "Delivered"}),
                          content_type="application/json")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(Client().post(f"/couriers/webhook/leopards/{old}/", {}).status_code, 401)

    def test_bad_token_rejected(self):
        r = self.post(webhook_token="short")
        self.assertEqual(r.status_code, 200)
        r = self.post(webhook_token="has spaces in it!!!!")
        self.assertEqual(r.status_code, 200)

    def test_custom_site_address(self):
        self.provider.webhook_base_url = "https://hooks.shanzee.com/"
        self.provider.save()
        self.assertEqual(self.provider.webhook_url(self.cred),
                         f"https://hooks.shanzee.com/couriers/webhook/leopards/{self.cred.webhook_token}/")


# ---------------------------------------------------------------------------
# sitemap-pages.xml editor
# ---------------------------------------------------------------------------
class SitemapPagesTests(SeoAdminTests):
    def test_public_address_overrides_local_site_url(self):
        with self.settings(SITE_URL="http://127.0.0.1:8000"):
            r = self.admin().post(reverse("storefront_seo"), self.form(site_address="https://shanzee.com/"))
            self.assertEqual(r.status_code, 302)
            xml = Client().get("/sitemap-pages.xml").content.decode()
            self.assertIn("<loc>https://shanzee.com/</loc>", xml)
            self.assertNotIn("127.0.0.1", xml)
            self.assertIn("https://shanzee.com/sitemap-products.xml", Client().get("/sitemap.xml").content.decode())
            self.assertIn("Sitemap: https://shanzee.com/sitemap.xml", Client().get("/robots.txt").content.decode())
            self.assertContains(Client().get("/"), '<link rel="canonical" href="https://shanzee.com/">')

    def test_default_lists_all_builtin_pages_on_site_domain(self):
        xml = Client().get("/sitemap-pages.xml").content.decode()
        for path in ["/", "/search-products/", "/best-deals/", "/blog/", "/Contact/", "/track-order/"]:
            self.assertIn(f"<loc>https://shop.test{path}</loc>", xml)
        self.assertNotIn("testserver", xml)

    def test_admin_chooses_pages_and_adds_extra(self):
        c = self.admin()
        r = c.post(reverse("storefront_seo"), self.form(
            sitemap_builtin_pages=["home", "shop", "blog"],
            sitemap_extra_pages="/about-us/\nhttps://shop.test/return-policy/ | 0.4 | monthly\n"))
        self.assertEqual(r.status_code, 302)
        xml = Client().get("/sitemap-pages.xml").content.decode()  # shows immediately (no cache)
        self.assertIn("<loc>https://shop.test/about-us/</loc>", xml)
        self.assertIn("<loc>https://shop.test/return-policy/</loc><changefreq>monthly</changefreq><priority>0.4</priority>", xml)
        self.assertNotIn("/track-order/", xml)
        page = c.get(reverse("storefront_seo"))
        self.assertContains(page, "https://shop.test/about-us/")
        self.assertContains(page, "Currently in sitemap-pages.xml (5)")

    def test_bad_extra_pages_rejected(self):
        c = self.admin()
        for bad in ["about-us", "https://evil.test/x", "/Adminpanel/", "/a/ | 3", "/a/ | 0.5 | sometimes"]:
            r = c.post(reverse("storefront_seo"), self.form(sitemap_builtin_pages=["home"], sitemap_extra_pages=bad))
            self.assertEqual(r.status_code, 200, bad)
            self.assertIn("sitemap_extra_pages", r.context["form"].errors, bad)
        r = c.post(reverse("storefront_seo"), self.form(sitemap_builtin_pages=[]))
        self.assertIn("sitemap_builtin_pages", r.context["form"].errors)
