"""
Admin panel: categories, session timeout, RBAC, dashboard, logging, friendly errors.

Run:  python manage.py test adminpanel
"""
import json
import tempfile
import time
from decimal import Decimal
from pathlib import Path
from unittest import mock

from django.conf import settings
from django.core.cache import cache
from django.contrib.auth.models import Group
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import Address, ErrorLog, SecurityEvent, User
from products.models import Category, Product, ProductVariant
from Web.models import Order, OrderItem

TEST_MEDIA = tempfile.mkdtemp(prefix="shanzee-test-media-")
CAT_API = "/Adminpanel/Products/api/v1/categories/"

def _png():
    from io import BytesIO
    from PIL import Image
    buf = BytesIO()
    Image.new("RGB", (4, 4), (91, 76, 240)).save(buf, "PNG")
    return buf.getvalue()


PNG = _png()


def make_user(email, role=None, staff=True, superuser=False):
    if superuser:
        return User.objects.create_superuser(email=email, password="Pw-Strong-123", full_name=email.split("@")[0])
    u = User.objects.create_user(email=email, password="Pw-Strong-123", full_name=email.split("@")[0], is_staff=staff)
    if role:
        u.groups.add(Group.objects.get(name=role))
    return u


def jwt(user):
    from rest_framework_simplejwt.tokens import AccessToken
    return {"HTTP_AUTHORIZATION": f"Bearer {AccessToken.for_user(user)}"}


class Base(TestCase):
    def setUp(self):
        from django.core.cache import cache
        cache.clear()  # rate-limit counters must not leak between tests
        from allauth.socialaccount.models import SocialApp
        SocialApp.objects.create(provider="google", name="Google", client_id="x", secret="y")
        self.root = make_user("root@x.com", superuser=True)
        self.catalog = make_user("catalog@x.com", "Catalog Manager")
        self.orders = make_user("orders@x.com", "Order Manager")
        self.analyst = make_user("analyst@x.com", "Analyst")
        self.support = make_user("support@x.com", "Support Agent")
        self.norole = make_user("norole@x.com")
        self.customer = make_user("cust@x.com", staff=False)


# ---------------------------------------------------------------------------
# Categories
# ---------------------------------------------------------------------------
@override_settings(MEDIA_ROOT=TEST_MEDIA)
class CategoryTests(Base):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.catalog)
        self.h = jwt(self.catalog)

    def post(self, data, url=CAT_API, method="post"):
        return getattr(self.client, method)(url, data, **self.h) if method == "post" else \
            self.client.generic(method.upper(), url, data=self._multipart(data), content_type=self._ct, **self.h)

    def _multipart(self, data):
        from django.test.client import BOUNDARY, encode_multipart
        self._ct = f"multipart/form-data; boundary={BOUNDARY}"
        return encode_multipart(BOUNDARY, data)

    def test_edit_updates_in_place_even_with_apostrophe(self):
        r = self.post({"name": "Men's Wear", "is_active": "1"})
        self.assertEqual(r.status_code, 201, r.content)
        cid = r.json()["id"]
        r = self.post({"name": "Men's Wear & Kurtas", "is_active": "0"}, url=f"{CAT_API}{cid}/", method="patch")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(Category.objects.count(), 1)  # edited, not duplicated
        c = Category.objects.get()
        self.assertEqual(c.name, "Men's Wear & Kurtas")
        self.assertFalse(c.is_active)

    def test_edit_keeps_parent(self):
        parent = Category.objects.create(name="Women")
        child = Category.objects.create(name="Lawn", parent=parent)
        r = self.post({"name": "Summer Lawn"}, url=f"{CAT_API}{child.pk}/", method="patch")
        self.assertEqual(r.status_code, 200)
        child.refresh_from_db()
        self.assertEqual(child.parent_id, parent.pk)

    def test_explore_lists_children_with_counts(self):
        parent = Category.objects.create(name="Women")
        lawn = Category.objects.create(name="Lawn", parent=parent)
        Category.objects.create(name="Printed", parent=lawn)
        Category.objects.create(name="Old", parent=lawn, is_deleted=True)
        top = self.client.get(CAT_API + "?parent=null", **self.h).json()
        self.assertEqual([c["name"] for c in top], ["Women"])
        self.assertEqual(top[0]["children_count"], 1)
        kids = self.client.get(f"{CAT_API}?parent={parent.pk}", **self.h).json()
        self.assertEqual([(c["name"], c["children_count"]) for c in kids], [("Lawn", 1)])
        self.assertEqual(self.client.get(CAT_API + "?parent=abc", **self.h).json(), [])

    def test_create_subcategory(self):
        parent = Category.objects.create(name="Women")
        r = self.post({"name": "Lawn", "parent": parent.pk})
        self.assertEqual(r.status_code, 201)
        self.assertEqual(Category.objects.get(name="Lawn").parent, parent)

    def test_duplicate_sibling_gives_friendly_error(self):
        Category.objects.create(name="Shoes")
        r = self.post({"name": "  shoes "})
        self.assertEqual(r.status_code, 400)
        self.assertIn("already exists", json.dumps(r.json()))
        # same name under another parent is fine
        p = Category.objects.create(name="Kids")
        self.assertEqual(self.post({"name": "Shoes", "parent": p.pk}).status_code, 201)

    def test_cannot_move_under_own_child(self):
        a = Category.objects.create(name="A")
        b = Category.objects.create(name="B", parent=a)
        r = self.post({"parent": b.pk}, url=f"{CAT_API}{a.pk}/", method="patch")
        self.assertEqual(r.status_code, 400)
        self.assertIn("under itself", json.dumps(r.json()))

    def test_delete_cascades_and_name_can_be_reused(self):
        a = Category.objects.create(name="A")
        b = Category.objects.create(name="B", parent=a)
        Category.objects.create(name="C", parent=b)
        self.assertEqual(self.client.delete(f"{CAT_API}{a.pk}/", **self.h).status_code, 204)
        self.assertEqual(Category.objects.filter(is_deleted=False).count(), 0)
        r = self.post({"name": "A"})  # used to crash with IntegrityError
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(r.json()["id"], a.pk)  # revived

    def test_image_validation_and_upload(self):
        bad = SimpleUploadedFile("x.txt", b"hello", content_type="text/plain")
        r = self.post({"name": "Bags", "image": bad})
        self.assertEqual(r.status_code, 400)  # no crash while logging a request that holds a file
        self.assertTrue(ErrorLog.objects.filter(severity="WARNING", status_code=400).exists())
        good = SimpleUploadedFile("x.png", PNG, content_type="image/png")
        r = self.post({"name": "Bags", "image": good})
        self.assertEqual(r.status_code, 201, r.content)
        self.assertTrue(r.json()["image"])

    def test_viewer_cannot_change(self):
        Category.objects.create(name="Shoes")
        c = Client(); c.force_login(self.analyst)
        self.assertEqual(c.get(CAT_API, **jwt(self.analyst)).status_code, 200)
        self.assertEqual(c.post(CAT_API, {"name": "X"}, **jwt(self.analyst)).status_code, 403)

    def test_page_renders_without_inline_json(self):
        Category.objects.create(name="Men's")
        r = self.client.get(reverse("categories"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "CategoryPage")
        self.assertNotContains(r, "fillCatgoryModal(${JSON.stringify")
        self.assertContains(r, "const CAN_EDIT = true")
        c = Client(); c.force_login(self.analyst)
        self.assertContains(c.get(reverse("categories")), "const CAN_EDIT = false")


# ---------------------------------------------------------------------------
# Session lifetime
# ---------------------------------------------------------------------------
@override_settings(ADMIN_SESSION_IDLE_MINUTES=30, ADMIN_SESSION_MAX_HOURS=8, ADMIN_SESSION_WARNING_SECONDS=120)
class SessionTests(Base):
    def login(self, user=None):
        user = user or self.root
        r = self.client.post(reverse("login"), {"username": user.email, "password": "Pw-Strong-123"})
        return r

    def age(self, idle=0, since_login=0):
        s = self.client.session
        now = int(time.time())
        s["_last_activity"] = now - idle
        s["_auth_at"] = now - since_login
        s.save()

    def test_staff_login_redirects_to_dashboard_and_expires_at_browser_close(self):
        r = self.login()
        self.assertRedirects(r, reverse("admin_dashboard"), fetch_redirect_response=False)
        self.assertTrue(self.client.session.get_expire_at_browser_close())
        self.assertTrue(SecurityEvent.objects.filter(event="login", user=self.root).exists())

    def test_customer_session_is_not_browser_bound(self):
        self.login(self.customer)
        self.assertFalse(self.client.session.get_expire_at_browser_close())

    def test_status_reports_remaining_and_does_not_extend(self):
        self.login()
        self.age(idle=600)
        d = self.client.get(reverse("admin_session_status")).json()
        self.assertAlmostEqual(d["remaining"], 1200, delta=5)
        self.assertEqual(d["warning"], 120)
        d2 = self.client.get(reverse("admin_session_status")).json()
        self.assertAlmostEqual(d2["remaining"], 1200, delta=5)  # unchanged

    def test_extend_resets_idle_timer(self):
        self.login()
        self.age(idle=1700)
        d = self.client.post(reverse("admin_session_extend"), {"manual": "1"}).json()
        self.assertAlmostEqual(d["remaining"], 1800, delta=5)
        self.assertTrue(SecurityEvent.objects.filter(event="session_extended").exists())

    def test_background_fetch_does_not_count_but_navigation_does(self):
        self.login()
        self.age(idle=900)
        self.client.get(CAT_API, HTTP_SEC_FETCH_MODE="cors", **jwt(self.root))
        left = self.client.get(reverse("admin_session_status")).json()["remaining"]
        self.assertAlmostEqual(left, 900, delta=5)
        self.client.get(reverse("categories"), HTTP_SEC_FETCH_MODE="navigate")
        left = self.client.get(reverse("admin_session_status")).json()["remaining"]
        self.assertAlmostEqual(left, 1800, delta=5)

    def test_idle_timeout_logs_out_page_request(self):
        self.login()
        self.age(idle=1801)
        r = self.client.get(reverse("categories"))
        self.assertEqual(r.status_code, 302)
        self.assertIn("expired=1", r["Location"])
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertTrue(SecurityEvent.objects.filter(event="session_timeout").exists())
        # login page explains why
        self.assertContains(self.client.get(r["Location"]), "Your session expired")

    def test_idle_timeout_api_gets_json_401(self):
        self.login()
        self.age(idle=5000)
        r = self.client.get(reverse("admin_session_status"))
        self.assertEqual(r.status_code, 401)
        self.assertEqual(r.json()["code"], "session_expired")

    def test_absolute_limit_even_when_active(self):
        self.login()
        self.age(idle=0, since_login=8 * 3600 + 1)
        r = self.client.get(reverse("admin_session_status"))
        self.assertEqual(r.status_code, 401)

    def test_page_carries_session_state_and_short_token_not_in_localstorage(self):
        self.login()
        r = self.client.get(reverse("admin_dashboard"))
        self.assertContains(r, "szSessionChip")
        self.assertContains(r, 'sessionStorage.setItem("access_token"')
        self.assertNotContains(r, 'localStorage.setItem("access_token"')
        self.assertNotContains(r, 'localStorage.setItem("refresh_token"')
        token = self.client.get(reverse("admin_session_token")).json()["access"]
        from rest_framework_simplejwt.tokens import AccessToken
        t = AccessToken(token)
        self.assertLessEqual(t["exp"] - int(time.time()), settings.ADMIN_JWT_MINUTES * 60 + 5)

    def test_logout_post(self):
        self.login()
        r = self.client.post(reverse("logout"))
        self.assertEqual(r.status_code, 302)
        self.assertTrue(SecurityEvent.objects.filter(event="logout").exists())


# ---------------------------------------------------------------------------
# RBAC
# ---------------------------------------------------------------------------
class RBACTests(Base):
    def status(self, user, url, method="get", **kw):
        c = Client()
        if user:
            c.force_login(user)
        return getattr(c, method)(url, **kw).status_code

    def test_matrix(self):
        cases = [
            # (user, url, expected)
            (self.root, reverse("admin_logs"), 200),
            (self.root, reverse("admin_team"), 200),
            (self.catalog, reverse("categories"), 200),
            (self.catalog, reverse("Orders"), 403),
            (self.catalog, reverse("admin_logs"), 403),
            (self.catalog, reverse("admin_dashboard"), 200),
            (self.orders, reverse("Orders"), 200),
            (self.orders, reverse("couriers:dashboard"), 200),
            (self.orders, reverse("categories"), 200),       # can view catalog
            (self.support, reverse("admin_dashboard"), 302),  # no dashboard -> first allowed page
            (self.support, reverse("couriers:settings"), 403),
            (self.analyst, reverse("sales_report"), 200),
            (self.analyst, reverse("admin_team"), 403),
            (self.norole, reverse("categories"), 403),
            (self.customer, reverse("categories"), 403),
        ]
        for user, url, expected in cases:
            with self.subTest(user=user.email, url=url):
                self.assertEqual(self.status(user, url), expected)

    def test_anonymous(self):
        c = Client()
        r = c.get(reverse("categories"))
        self.assertEqual(r.status_code, 302)
        self.assertIn("next=", r["Location"])
        r = c.get(CAT_API)
        self.assertEqual(r.status_code, 401)
        self.assertEqual(r.json()["code"], "not_authenticated")

    def test_unsafe_methods_need_manage_permission(self):
        Category.objects.create(name="Shoes")
        c = Client(); c.force_login(self.orders)
        self.assertEqual(c.get(CAT_API, **jwt(self.orders)).status_code, 200)
        self.assertEqual(c.post(CAT_API, {"name": "X"}, **jwt(self.orders)).status_code, 403)
        self.assertTrue(SecurityEvent.objects.filter(event="access_denied", user=self.orders).exists())

    def test_jwt_only_client(self):
        c = Client()
        self.assertEqual(c.get(CAT_API, **jwt(self.catalog)).status_code, 200)
        self.assertEqual(c.get(CAT_API, **jwt(self.customer)).status_code, 403)

    def test_menu_follows_permissions(self):
        c = Client(); c.force_login(self.catalog)
        html = c.get(reverse("categories")).content.decode()
        self.assertIn(reverse("products"), html)
        self.assertNotIn(reverse("Orders"), html)
        self.assertNotIn(reverse("admin_logs"), html)

    def test_team_update(self):
        c = Client(); c.force_login(self.root)
        r = c.post(reverse("admin_team_update", args=[self.norole.pk]), {"roles": ["Analyst", "Support Agent"]})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(set(self.norole.groups.values_list("name", flat=True)), {"Analyst", "Support Agent"})
        self.assertTrue(SecurityEvent.objects.filter(event="roles_changed").exists())
        r = c.post(reverse("admin_team_update", args=[self.norole.pk]), {"roles": ["Hacker"]})
        self.assertEqual(r.status_code, 400)
        r = c.post(reverse("admin_team_add"), {"email": self.customer.email, "role": "Analyst"})
        self.assertEqual(r.status_code, 200)
        self.customer.refresh_from_db()
        self.assertTrue(self.customer.is_staff)
        # a non-superuser can't manage roles
        c2 = Client(); c2.force_login(make_user("adm@x.com", "Administrator"))
        self.assertEqual(c2.post(reverse("admin_team_update", args=[self.norole.pk]), {"roles": []}).status_code, 403)


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------
@override_settings(MEDIA_ROOT=TEST_MEDIA)
class DashboardTests(Base):
    def setUp(self):
        super().setUp()
        cat = Category.objects.create(name="Lawn")
        p = Product.objects.create(name="Suit", sku="S1", price=Decimal("1000"), stock_quantity=50)
        p.category.set([cat])
        v = ProductVariant.objects.create(product=p, name="M", sku="S1M", price=Decimal("1000"), stock_quantity=50)
        low = ProductVariant.objects.create(product=p, name="XL", sku="S1XL", price=Decimal("1000"), stock_quantity=2)
        addr = Address.objects.create(user=self.customer, full_name="C", phone="0300", street_address="s",
                                      city="Lahore", postal_code="1")
        for total, status, method in [(1000, "delivered", "cod"), (2000, "processing", "card"), (500, "cancelled", "cod")]:
            o = Order.objects.create(user=self.customer, shipping_address=addr, billing_address=addr,
                                     total_amount=Decimal(total), status=status, payment_method=method)
            OrderItem.objects.create(order=o, product=p, variant=v, quantity=1, price=Decimal(total))

    def test_page_and_data(self):
        c = Client(); c.force_login(self.analyst)
        r = c.get(reverse("admin_dashboard"))
        self.assertContains(r, "chartTrend")
        d = c.get(reverse("admin_dashboard_data") + "?range=7d").json()
        k = {x["key"]: x for x in d["kpis"]}
        self.assertEqual(k["revenue"]["value"], 3000.0)   # cancelled excluded
        self.assertEqual(k["orders"]["value"], 3)
        self.assertEqual(k["aov"]["value"], 1500.0)
        self.assertAlmostEqual(k["loss_rate"]["value"], 33.3, places=1)
        self.assertEqual(d["snapshot"]["low_stock"], 1)
        self.assertEqual(len(d["trends"]["labels"]), 7)
        self.assertEqual(sum(d["trends"]["orders"]), 3)
        self.assertEqual(d["breakdowns"]["categories"][0]["label"], "Lawn")
        self.assertEqual(len(d["breakdowns"]["hours"]), 24)
        self.assertEqual(len(d["recent"]["orders"]), 3)

    def test_ranges(self):
        c = Client(); c.force_login(self.root)
        today = timezone.localdate()
        d = c.get(reverse("admin_dashboard_data"), {"range": "custom", "from": str(today), "to": "2000-01-01"}).json()
        self.assertEqual(d["range"]["to"], str(today))   # swapped + clamped, no crash
        d = c.get(reverse("admin_dashboard_data"), {"range": "custom", "from": "nope"}).json()
        self.assertEqual(d["range"]["key"], "30d")
        d = c.get(reverse("admin_dashboard_data"), {"range": "365d"}).json()
        self.assertEqual(d["trends"]["unit"], "week")

    def test_no_dashboard_permission(self):
        c = Client(); c.force_login(self.support)
        self.assertEqual(c.get(reverse("admin_dashboard_data")).status_code, 403)


# ---------------------------------------------------------------------------
# Errors & logging
# ---------------------------------------------------------------------------
class ErrorAndLoggingTests(Base):
    def test_friendly_404(self):
        with override_settings(DEBUG=False):
            r = self.client.get("/Adminpanel/Products/does-not-exist/xyz/")
        self.assertIn(r.status_code, (403, 404, 302))
        c = Client(); c.force_login(self.root)
        with override_settings(DEBUG=False):
            r = c.get("/no-such-page-here/")
        self.assertEqual(r.status_code, 404)
        self.assertContains(r, "Page not found", status_code=404)
        self.assertContains(r, "Reference", status_code=404)
        self.assertTrue(r["X-Request-ID"])

    def test_unhandled_api_error_is_clean_json_and_logged(self):
        c = Client(raise_request_exception=False); c.force_login(self.root)
        with mock.patch("products.views.CategoryViewSet.list", side_effect=RuntimeError("db exploded at line 42")):
            r = c.get(CAT_API, **jwt(self.root))
        self.assertEqual(r.status_code, 500)
        body = r.json()
        self.assertEqual(body["detail"], "Something went wrong. Please try again.")
        self.assertNotIn("exploded", r.content.decode())
        self.assertNotIn("Traceback", r.content.decode())
        log = ErrorLog.objects.get(severity="ERROR")
        self.assertIn("db exploded", log.error_message)
        self.assertIn("Traceback", log.stack_trace)
        self.assertEqual(log.request_id, body["reference"])

    def test_unhandled_page_error_friendly(self):
        c = Client(raise_request_exception=False); c.force_login(self.root)
        with override_settings(DEBUG=False), \
                mock.patch("adminpanel.views.rbac.role_names", side_effect=ValueError("secret detail")):
            r = c.get(reverse("admin_team"))
        self.assertEqual(r.status_code, 500)
        self.assertNotIn("secret detail", r.content.decode())
        self.assertTrue(ErrorLog.objects.filter(error_message__contains="secret detail").exists())

    def test_failed_login_and_rate_limit_are_audited(self):
        for _ in range(3):
            self.client.post(reverse("login"), {"username": "root@x.com", "password": "wrong"})
        self.assertEqual(SecurityEvent.objects.filter(event="login_failed").count(), 3)

    def test_log_files_are_json_with_context(self):
        c = Client(raise_request_exception=False); c.force_login(self.root)
        with mock.patch("products.views.CategoryViewSet.list", side_effect=RuntimeError("file log check")):
            c.get(CAT_API, **jwt(self.root))
        for h in __import__("logging").getLogger("app").handlers:
            h.flush()
        lines = (Path(settings.LOG_DIR) / "error.log").read_text().strip().splitlines()
        entry = [json.loads(x) for x in lines if "file log check" in x][-1]
        self.assertEqual(entry["level"], "ERROR")
        self.assertIn("file log check", entry["message"])
        for key in ("ts", "request_id", "path", "method", "ip", "exception"):
            self.assertIn(key, entry)
        sec = (Path(settings.LOG_DIR) / "security.log").read_text()
        self.assertIn('"logger": "security"', sec)

    def test_logs_page_filters(self):
        c = Client(); c.force_login(self.root)
        c.post(reverse("login"), {"username": "nobody@x.com", "password": "x"})
        r = c.get(reverse("admin_logs"), {"tab": "security", "event": "login_failed"})
        self.assertContains(r, "login_failed")
        e = SecurityEvent.objects.filter(event="login_failed").first()
        self.assertEqual(c.get(reverse("admin_log_detail", args=["security", e.pk])).status_code, 200)

    def test_sensitive_data_masked_in_logs(self):
        from accounts.error_logging import _clean
        out = _clean({"password": "hunter2", "api_key": "k", "name": "ok", "nested": {"token": "t"}})
        self.assertEqual(out["password"], "***")
        self.assertEqual(out["api_key"], "***")
        self.assertEqual(out["nested"]["token"], "***")
        self.assertEqual(out["name"], "ok")


class AllAdminPagesRender(Base):
    """Every admin page still renders for a super admin under the new layout."""

    def test_pages(self):
        c = Client(); c.force_login(self.root)
        names = ["admin_dashboard", "admin_logs", "admin_team", "categories", "brands", "attributes", "products",
                 "Orders", "inventory-page", "promotions_page", "Blog-post", "topbar_manage", "picture-page",
                 "wishlist", "wish_to_buy_admin", "UserList", "AdminTicketList", "admin_messages",
                 "StaffQuestionList", "AdminReviewsPage", "admin-withdrawals", "sales_report", "inventory_report",
                 "customer_analytics", "revenue_profit", "order_stats", "couriers:dashboard", "couriers:settings",
                 "addProduct", "users-page"]
        for name in names:
            with self.subTest(name=name):
                r = c.get(reverse(name))
                self.assertEqual(r.status_code, 200, name)
                self.assertContains(r, "sz-sidebar")
        r = c.get(reverse("OrdersByStatus", args=["pending"]))
        self.assertEqual(r.status_code, 200)


class LoginRedirectTests(Base):
    """Signing in on the login page used to send people back to the login page."""

    def test_login_page_referer_is_not_a_target(self):
        r = self.client.post(reverse("login_api"), {"username": self.root.email, "password": "Pw-Strong-123"},
                             HTTP_REFERER="http://testserver/api/v1/login/")
        self.assertEqual(r.json()["redirect"], "/Adminpanel/")
        c = Client()
        r = c.post(reverse("login_api"), {"username": self.customer.email, "password": "Pw-Strong-123"},
                   HTTP_REFERER="http://testserver/api/v1/login/")
        self.assertEqual(r.json()["redirect"], "/")

    def test_next_from_login_page_url_is_honoured(self):
        r = self.client.post(reverse("login_api"), {"username": self.root.email, "password": "Pw-Strong-123"},
                             HTTP_REFERER="http://testserver/api/v1/login/?expired=1&next=/Adminpanel/Products/categories/")
        self.assertEqual(r.json()["redirect"], "/Adminpanel/Products/categories/")

    def test_product_page_referer_still_works_and_external_next_rejected(self):
        c = Client()
        r = c.post(reverse("login_api"), {"username": self.customer.email, "password": "Pw-Strong-123"},
                   HTTP_REFERER="http://testserver/product/5/")
        self.assertEqual(r.json()["redirect"], "/product/5/")
        c = Client()
        r = c.post(reverse("login_api") + "?next=https://evil.example/", {"username": self.customer.email,
                                                                          "password": "Pw-Strong-123"})
        self.assertEqual(r.json()["redirect"], "/")


class EmailDiagnosisTests(Base):
    SMTP = "django.core.mail.backends.smtp.EmailBackend"

    def post_otp(self):
        c = Client(); c.force_login(self.root)
        return c.post(reverse("admin_otp_request", args=["download"]))

    def test_missing_password_is_explained_and_logged(self):
        with override_settings(EMAIL_BACKEND=self.SMTP, EMAIL_HOST_PASSWORD=""):
            r = self.post_otp()
        self.assertEqual(r.status_code, 502)
        self.assertIn("SMTP_PASSWORD", r.json()["detail"])
        self.assertTrue(ErrorLog.objects.filter(error_message__contains="SMTP_PASSWORD").exists())

    def test_smtp_errors_are_explained(self):
        import smtplib, socket
        cases = [
            (smtplib.SMTPAuthenticationError(535, b"auth failed"), "rejected the login"),
            (smtplib.SMTPSenderRefused(553, b"not owned", "shanzee@shanzee.com"), "Set SMTP_FROM"),
            (socket.timeout("timed out"), "Timed out"),
            (ConnectionRefusedError(111, "refused"), "Couldn't connect"),
        ]
        for exc, expected in cases:
            with self.subTest(exc=type(exc).__name__), \
                    override_settings(EMAIL_BACKEND=self.SMTP, EMAIL_HOST_PASSWORD="x"), \
                    mock.patch("django.core.mail.backends.smtp.EmailBackend.send_messages", side_effect=exc):
                cache.clear()
                r = self.post_otp()
                self.assertEqual(r.status_code, 502)
                self.assertIn(expected, r.json()["detail"])
                self.assertNotIn('"x"', r.content.decode())

    def test_test_email_button(self):
        c = Client(); c.force_login(self.root)
        r = c.post(reverse("admin_email_test"))
        self.assertEqual(r.status_code, 200)
        self.assertIn("Test email sent", r.json()["message"])
        with override_settings(EMAIL_BACKEND=self.SMTP, EMAIL_HOST_PASSWORD=""):
            r = c.post(reverse("admin_email_test"))
        self.assertEqual(r.status_code, 502)
        analyst = make_user("an2@x.com", "Analyst")
        c2 = Client(); c2.force_login(analyst)
        self.assertEqual(c2.post(reverse("admin_email_test")).status_code, 403)
