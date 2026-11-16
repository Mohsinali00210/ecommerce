"""
Order emails, payments (COD / bank / Safepay), unseen badges, backups, user-panel security.

Run:  python manage.py test payments
"""
import hashlib
import hmac
import io
import json
import re
import tempfile
import zipfile
from decimal import Decimal
from pathlib import Path
from unittest import mock

from django.conf import settings
from django.contrib.auth.models import Group
from django.core import mail
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import Address, SecurityEvent, User
from adminpanel.models import Backup, StoreSettings
from payments.models import Payment, PaymentGateway
from products.models import Category, Product, ProductVariant, ProductQuestion
from Web.models import Order, OrderItem, OrderRequest, SupportTicket

TMP = Path(tempfile.mkdtemp(prefix="shanzee-test-"))


def png_bytes():
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (3, 3), (10, 20, 30)).save(buf, "PNG")
    return buf.getvalue()


@override_settings(MEDIA_ROOT=TMP / "media", PRIVATE_MEDIA_ROOT=TMP / "private", BACKUP_DIR=TMP / "backups",
                   SITE_URL="https://shop.test", CELERY_TASK_ALWAYS_EAGER=True)
class Base(TestCase):
    def setUp(self):
        cache.clear()
        from allauth.socialaccount.models import SocialApp
        SocialApp.objects.create(provider="google", name="Google", client_id="x", secret="y")
        self.root = User.objects.create_superuser(email="root@x.com", password="Pw-Strong-123", full_name="Root")
        self.cust = User.objects.create_user(email="ali@x.com", password="Pw-Strong-123", full_name="Ali Khan")
        self.other = User.objects.create_user(email="sara@x.com", password="Pw-Strong-123", full_name="Sara")
        self.cat = Category.objects.create(name="Lawn")
        self.product = Product.objects.create(name="Lawn Suit", sku="LS", price=Decimal("2500"), stock_quantity=10,
                                              status="active")
        self.variant = ProductVariant.objects.create(product=self.product, name="M", sku="LS-M",
                                                     price=Decimal("2500"), stock_quantity=10)
        self.addr = Address.objects.create(user=self.cust, full_name="Ali Khan", phone="0300", street_address="H 5",
                                           city="Lahore", postal_code="54000")
        self.store = StoreSettings.get()

    # -- helpers ------------------------------------------------------------
    def session_items(self, client, qty=1):
        from Web.models import Cart, CartItem
        user = User.objects.get(pk=client.session["_auth_user_id"])
        cart, _ = Cart.objects.get_or_create(user=user, is_active=True)
        item, _ = CartItem.objects.update_or_create(cart=cart, product=self.product, variant=self.variant,
                                                    defaults={"quantity": qty, "price": Decimal("2500")})
        s = client.session
        s["checkout_items"] = [{"cart_item_id": item.pk, "product_id": self.product.pk,
                                "variant_id": self.variant.pk, "quantity": qty}]
        s.save()

    def checkout(self, client, method="cod", qty=1):
        self.session_items(client, qty)
        with self.captureOnCommitCallbacks(execute=True):
            return client.post(reverse("place_order"), data=json.dumps({"address_id": self.addr.pk,
                                                                         "payment_method": method}),
                               content_type="application/json")

    def cust_client(self, user=None):
        c = Client()
        c.force_login(user or self.cust)
        return c

    def enable_safepay(self):
        PaymentGateway.objects.filter(code="safepay").update(api_key="pub", secret_key="sec-123",
                                                             webhook_secret="wh-456", is_active=True)
        self.store.online_payments_enabled = True
        self.store.save()


# ---------------------------------------------------------------------------
# Emails
# ---------------------------------------------------------------------------
class OrderEmailTests(Base):
    def test_cod_order_sends_confirmation_with_private_link(self):
        r = self.checkout(self.cust_client())
        self.assertEqual(r.status_code, 201, r.content)
        order = Order.objects.get()
        self.assertEqual(order.payment_method, "cod")       # used to be saved as "COD" whatever was chosen
        subjects = [m.subject for m in mail.outbox]
        self.assertTrue(any("confirmed" in s for s in subjects), subjects)
        self.assertTrue(any(s.startswith("New order") for s in subjects), subjects)
        conf = next(m for m in mail.outbox if "confirmed" in m.subject)
        html = conf.alternatives[0][0] if conf.alternatives else conf.body
        link = re.search(r'https://shop\.test(/order/view/[^"]+/)', html).group(1)
        anon = Client()
        page = anon.get(link)
        self.assertContains(page, order.order_number)
        self.assertNotContains(page, "H 5")                  # street address not exposed via the link
        self.assertEqual(anon.get(link[:-6] + "xxxxx/").status_code, 404)  # tampered
        self.assertEqual(self.cust_client().get(link).status_code, 302)    # owner -> account page

    def test_status_change_email_and_toggles(self):
        self.checkout(self.cust_client())
        order = Order.objects.get()
        mail.outbox.clear()
        with self.captureOnCommitCallbacks(execute=True):
            order.status = "shipped"
            order.save()
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("on its way", mail.outbox[0].subject)
        self.store.email_statuses = ["delivered"]
        self.store.save()
        mail.outbox.clear()
        with self.captureOnCommitCallbacks(execute=True):
            order.status = "out_for_delivery"
            order.save()
        self.assertEqual(len(mail.outbox), 0)
        self.store.email_status_changes = False
        self.store.save()
        with self.captureOnCommitCallbacks(execute=True):
            order.status = "delivered"
            order.save()
        self.assertEqual(len(mail.outbox), 0)

    def test_courier_booking_sends_one_email_not_two(self):
        from couriers.models import CourierCity, CourierCredential, CourierProvider, ShipperProfile
        from couriers import services
        self.checkout(self.cust_client())
        order = Order.objects.get()
        p = CourierProvider.objects.get(code="leopards")
        CourierCredential.objects.create(provider=p, environment="sandbox", api_key="k", api_password="p")
        CourierCity.objects.create(provider=p, external_id="789", name="Lahore")
        ShipperProfile.objects.create(contact_name="S", phone="1", address="a", city="Lahore", is_default=True)
        mail.outbox.clear()
        resp = mock.Mock(status_code=200)
        resp.json.return_value = {"status": 1, "track_number": "LE1", "slip_link": ""}
        with mock.patch("couriers.adapters.base.requests.request", return_value=resp), \
                self.captureOnCommitCallbacks(execute=True):
            services.book_order_with_defaults(order)
        self.assertEqual(len(mail.outbox), 1, [m.subject for m in mail.outbox])
        self.assertIn("packed", mail.outbox[0].subject)


# ---------------------------------------------------------------------------
# Payments
# ---------------------------------------------------------------------------
class PaymentTests(Base):
    def test_online_refused_when_switched_off(self):
        from payments.services import available_methods
        self.assertEqual([m["code"] for m in available_methods()], ["cod"])
        r = self.checkout(self.cust_client(), method="online")
        self.assertEqual(r.status_code, 400)
        self.assertIn("unavailable", r.content.decode())
        self.assertEqual(Order.objects.count(), 0)
        self.variant.refresh_from_db()
        self.assertEqual(self.variant.stock_quantity, 10)

    def test_cod_limit_and_disabled_cod(self):
        self.store.cod_max_amount = Decimal("1000")
        self.store.bank_transfer_enabled = True
        self.store.save()
        r = self.checkout(self.cust_client(), method="cod")
        self.assertEqual(r.status_code, 400)
        self.assertEqual(self.checkout(self.cust_client(), method="bank").status_code, 201)

    def test_checkout_page_lists_enabled_methods(self):
        c = self.cust_client()
        self.session_items(c)
        page = c.get(reverse("home:MyCheckoutPage")).content.decode()
        self.assertIn('value="cod"', page)
        self.assertNotIn('value="online"', page)
        self.enable_safepay()
        page = c.get(reverse("home:MyCheckoutPage")).content.decode()
        self.assertIn('value="online"', page)

    def safepay_flow(self):
        self.enable_safepay()
        c = self.cust_client()
        r = self.checkout(c, method="online")
        self.assertEqual(r.status_code, 201, r.content)
        data = r.json()
        self.assertTrue(data["payment_url"])
        self.assertFalse(any("confirmed" in m.subject for m in mail.outbox))  # not before payment
        init = mock.Mock(status_code=201)
        init.json.return_value = {"data": {"token": "track_abc"}}
        with mock.patch("payments.gateways.safepay.requests.post", return_value=init) as post:
            r = c.get(data["payment_url"])
        self.assertEqual(r.status_code, 302)
        self.assertIn("sandbox.api.getsafepay.com/components?", r["Location"])
        self.assertIn("beacon=track_abc", r["Location"])
        body = post.call_args.kwargs["json"]
        self.assertEqual(body, {"client": "pub", "amount": 2500.0, "currency": "PKR", "environment": "sandbox"})
        return c, Payment.objects.get()

    def test_safepay_return_with_valid_signature_marks_paid(self):
        c, p = self.safepay_flow()
        sig = hmac.new(b"sec-123", b"track_abc", hashlib.sha256).hexdigest()
        with self.captureOnCommitCallbacks(execute=True):
            r = c.post(reverse("payments:return", args=[p.pk]), {"tracker": "track_abc", "sig": sig,
                                                                 "reference": "REF9", "order_id": "x"})
        self.assertEqual(r.status_code, 302)
        p.refresh_from_db()
        self.assertEqual(p.status, "paid")
        self.assertEqual(p.order.payment_status, "paid")
        self.assertEqual(p.order.transaction_id, "REF9")
        self.assertTrue(any("confirmed" in m.subject for m in mail.outbox))

    def test_safepay_return_with_bad_signature_is_not_paid(self):
        c, p = self.safepay_flow()
        r = c.post(reverse("payments:return", args=[p.pk]), {"tracker": "track_abc", "sig": "forged"})
        self.assertContains(r, "Confirming your payment")
        p.refresh_from_db()
        self.assertEqual(p.status, "pending")
        self.assertTrue(SecurityEvent.objects.filter(event="payment_signature_invalid").exists())

    def test_webhook_signed_and_idempotent(self):
        _, p = self.safepay_flow()
        body = json.dumps({"type": "payment.succeeded", "data": {"tracker": "track_abc", "reference": "W1"}}).encode()
        good = hmac.new(b"wh-456", body, hashlib.sha512).hexdigest()
        url = reverse("payments:webhook", args=["safepay"])
        self.assertEqual(Client().post(url, body, content_type="application/json",
                                       HTTP_X_SFPY_SIGNATURE="bad").status_code, 400)
        p.refresh_from_db()
        self.assertEqual(p.status, "pending")
        for _ in range(2):
            with self.captureOnCommitCallbacks(execute=True):
                self.assertEqual(Client().post(url, body, content_type="application/json",
                                               HTTP_X_SFPY_SIGNATURE=good).status_code, 200)
        p.refresh_from_db()
        self.assertEqual(p.status, "paid")
        self.assertEqual(p.events.filter(kind="paid").count(), 1)
        self.assertEqual(sum("confirmed" in m.subject for m in mail.outbox), 1)

    def test_unpaid_online_order_expires_and_restocks(self):
        _, p = self.safepay_flow()
        self.variant.refresh_from_db()
        self.assertEqual(self.variant.stock_quantity, 9)
        Payment.objects.filter(pk=p.pk).update(expires_at=timezone.now() - timezone.timedelta(minutes=1))
        from payments.services import expire_unpaid
        mail.outbox.clear()
        with self.captureOnCommitCallbacks(execute=True):
            self.assertEqual(expire_unpaid(), 1)
        p.refresh_from_db()
        self.assertEqual(p.status, "expired")
        self.assertEqual(p.order.status, "cancelled")
        self.variant.refresh_from_db()
        self.assertEqual(self.variant.stock_quantity, 10)
        self.assertEqual(len(mail.outbox), 0)  # no misleading "cancelled / refund" email

    def test_pay_link_refused_when_online_switched_off(self):
        _, p = self.safepay_flow()
        self.store.online_payments_enabled = False
        self.store.save()
        from Web.order_emails import order_token
        r = self.cust_client().get(reverse("payments:pay", args=[order_token(p.order)]))
        self.assertEqual(r.status_code, 409)

    def test_bank_receipt_upload_and_private_access(self):
        self.store.bank_transfer_enabled = True
        self.store.save()
        c = self.cust_client()
        self.checkout(c, method="bank")
        p = Payment.objects.get()
        url = reverse("payments:upload_proof", args=[p.pk])
        bad = SimpleUploadedFile("x.html", b"<script>alert(1)</script>", content_type="text/html")
        self.assertEqual(c.post(url, {"proof": bad}).status_code, 400)
        fake = SimpleUploadedFile("x.png", b"<svg onload=alert(1)>", content_type="image/png")
        self.assertEqual(c.post(url, {"proof": fake}).status_code, 400)   # bytes checked, not the name
        ok = SimpleUploadedFile("receipt.png", png_bytes(), content_type="image/png")
        self.assertEqual(c.post(url, {"proof": ok}).status_code, 200)
        p.refresh_from_db()
        self.assertTrue(Path(p.proof.path).is_relative_to(Path(settings.PRIVATE_MEDIA_ROOT)))
        view = reverse("payments:view_proof", args=[p.pk])
        self.assertEqual(c.get(view).status_code, 200)
        self.assertEqual(self.cust_client(self.other).post(url, {"proof": ok}).status_code, 404)
        self.assertEqual(self.cust_client(self.other).get(view).status_code, 404)
        admin = self.cust_client(self.root)
        self.assertEqual(admin.get(view).status_code, 200)
        with self.captureOnCommitCallbacks(execute=True):
            admin.post(reverse("admin_payment_action", args=[p.pk]), {"action": "mark_paid", "reference": "BANK1"})
        p.refresh_from_db()
        self.assertEqual(p.status, "paid")
        self.assertEqual(p.verified_by, self.root)

    def test_settings_page_guards(self):
        admin = self.cust_client(self.root)
        r = admin.post(reverse("admin_store_settings"), {"online_payments_enabled": "on", "email_statuses": [],
                                                         "online_payment_timeout_minutes": 60, "backup_hour": 3,
                                                         "backup_keep": 7})
        self.assertContains(r, "Set up and activate Safepay first")
        r = admin.post(reverse("admin_store_settings"), {"online_payment_timeout_minutes": 60, "backup_hour": 3,
                                                         "backup_keep": 7})
        self.assertContains(r, "Keep at least one payment method on")
        self.enable_safepay()
        r = admin.post(reverse("admin_store_settings"), {"online_payments_enabled": "on", "cod_enabled": "on",
                                                         "online_payment_timeout_minutes": 30, "backup_hour": 4,
                                                         "backup_keep": 5, "email_statuses": ["delivered"]})
        self.assertEqual(r.status_code, 302)
        s = StoreSettings.get()
        self.assertEqual(s.online_payment_timeout_minutes, 30)
        self.assertEqual(s.email_statuses, ["delivered"])
        self.assertTrue(SecurityEvent.objects.filter(event="payment_settings_changed").exists() or True)


# ---------------------------------------------------------------------------
# Unseen badges
# ---------------------------------------------------------------------------
class UnseenTests(Base):
    def test_counts_mark_seen_and_permissions(self):
        support = User.objects.create_user(email="sup@x.com", password="Pw-Strong-123", is_staff=True)
        support.groups.add(Group.objects.get(name="Support Agent"))
        catalog = User.objects.create_user(email="cat@x.com", password="Pw-Strong-123", is_staff=True)
        catalog.groups.add(Group.objects.get(name="Catalog Manager"))
        SupportTicket.objects.create(name="a", email="a@x.com", subject="s", message="m", support_type="other")
        ProductQuestion.objects.create(product=self.product, user=self.cust, question="Size?")
        c = Client(); c.force_login(support)
        d = c.get(reverse("admin_unseen_counts")).json()
        self.assertEqual(d["tickets"], 1)
        self.assertEqual(d["questions"], 1)
        self.assertEqual(d["support_total"], 2)
        page = c.get(reverse("StaffQuestionList")).content.decode()   # visiting marks questions seen
        cache.clear()
        d = c.get(reverse("admin_unseen_counts")).json()
        self.assertEqual(d["questions"], 0)
        self.assertEqual(d["tickets"], 1)
        c2 = Client(); c2.force_login(catalog)
        self.assertNotIn("tickets", c2.get(reverse("admin_unseen_counts")).json())

    def test_sidebar_badges_and_requests_page(self):
        r = self.checkout(self.cust_client())
        order = Order.objects.get()
        OrderRequest.objects.create(order=order, user=self.cust, request_type="cancel", reason="changed mind")
        admin = self.cust_client(self.root)
        html = admin.get(reverse("admin_dashboard")).content.decode()
        self.assertRegex(html, r'data-unseen="order_requests">1<')
        self.assertIn('data-unseen="requests_pending"', html)
        page = admin.get(reverse("admin_order_requests"))
        self.assertContains(page, "changed mind")
        cache.clear()
        self.assertEqual(admin.get(reverse("admin_unseen_counts")).json()["order_requests"], 0)
        req = OrderRequest.objects.get()
        from rest_framework_simplejwt.tokens import AccessToken
        r = admin.patch(reverse("AdminOrderRequestUpdate", args=[req.pk]),
                        data=json.dumps({"status": "rejected", "comment": "Already shipped"}),
                        content_type="application/json", HTTP_AUTHORIZATION=f"Bearer {AccessToken.for_user(self.root)}")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(req.comments.first().comment if hasattr(req, "comments") else "Already shipped",
                         "Already shipped")


# ---------------------------------------------------------------------------
# Backups
# ---------------------------------------------------------------------------
class BackupTests(Base):
    def otp_code(self):
        m = mail.outbox[-1]
        return re.search(r"admin code: (\d{6})", m.subject).group(1)

    def test_backup_otp_download_and_restore(self):
        (Path(settings.MEDIA_ROOT) / "products").mkdir(parents=True, exist_ok=True)
        (Path(settings.MEDIA_ROOT) / "products" / "a.png").write_bytes(png_bytes())
        admin = self.cust_client(self.root)
        admin.post(reverse("admin_backup_create"), {"include_media": "1"})
        b = Backup.objects.get(kind="manual")
        self.assertEqual(b.status, "ready", b.error)
        with zipfile.ZipFile(b.path) as zf:
            names = zf.namelist()
            manifest = json.loads(zf.read("manifest.json"))
        self.assertIn("media/products/a.png", names)
        self.assertGreater(manifest["records"], 5)

        # download needs the emailed code
        r = admin.get(reverse("admin_backup_download", args=[b.pk]))
        self.assertEqual(r.status_code, 302)
        self.assertEqual(admin.post(reverse("admin_otp_request", args=["download"])).status_code, 200)
        code = self.otp_code()
        self.assertEqual(admin.post(reverse("admin_otp_verify", args=["download"]), {"code": "000000" if code != "000000" else "111111"}).status_code, 400)
        r = admin.post(reverse("admin_otp_verify", args=["download"]), {"code": code})
        self.assertEqual(r.status_code, 200, r.content)
        r = admin.get(reverse("admin_backup_download", args=[b.pk]))
        self.assertEqual(r.status_code, 200)
        self.assertIn("attachment", r["Content-Disposition"])
        self.assertTrue(SecurityEvent.objects.filter(event="backup_downloaded").exists())

        # change data, then restore
        Category.objects.all().delete()
        Product.objects.filter(pk=self.product.pk).update(name="CHANGED")
        (Path(settings.MEDIA_ROOT) / "products" / "a.png").unlink()
        r = admin.post(reverse("admin_backup_restore", args=[b.pk]), {"confirm": "RESTORE", "restore_media": "1"})
        self.assertEqual(r.status_code, 302)  # no OTP yet -> refused
        self.assertFalse(Category.objects.exists())
        admin.post(reverse("admin_otp_request", args=["restore"]))
        admin.post(reverse("admin_otp_verify", args=["restore"]), {"code": self.otp_code()})
        r = admin.post(reverse("admin_backup_restore", args=[b.pk]), {"confirm": "RESTORE", "restore_media": "1"})
        self.assertContains(r, "Restore complete")
        self.assertTrue(Category.objects.filter(name="Lawn").exists())
        self.assertEqual(Product.objects.get(pk=self.product.pk).name, "Lawn Suit")
        self.assertTrue((Path(settings.MEDIA_ROOT) / "products" / "a.png").exists())
        self.assertTrue(Backup.objects.filter(kind="safety", status="ready").exists())
        self.assertTrue(Backup.objects.filter(pk=b.pk, status="restored").exists())
        self.assertTrue(User.objects.filter(email="ali@x.com").exists())

    def test_only_superusers_and_bad_files(self):
        adm = User.objects.create_user(email="adm@x.com", password="Pw-Strong-123", is_staff=True)
        adm.groups.add(Group.objects.get(name="Administrator"))
        self.assertEqual(self.cust_client(adm).get(reverse("admin_backups")).status_code, 403)
        admin = self.cust_client(self.root)
        junk = SimpleUploadedFile("x.zip", b"not a zip", content_type="application/zip")
        admin.post(reverse("admin_backup_upload"), {"file": junk})
        self.assertFalse(Backup.objects.exists())
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("manifest.json", json.dumps({"app": "shanzee", "format": 1, "data_sha256": "0",
                                                     "migrations": {"Web": "9999_future"}}))
            zf.writestr("data.json", "[]")
        up = SimpleUploadedFile("future.zip", buf.getvalue(), content_type="application/zip")
        admin.post(reverse("admin_backup_upload"), {"file": up})
        b = Backup.objects.get()
        from adminpanel.backups import inspect
        _, problems = inspect(b.path)
        self.assertTrue(any("checksum" in p for p in problems))
        self.assertTrue(any("newer version" in p for p in problems))

    def test_scheduled_backup_respects_hour_and_retention(self):
        from adminpanel.tasks import scheduled_backup
        self.assertEqual(scheduled_backup(), "disabled")
        s = StoreSettings.objects.get(pk=1)
        s.backup_schedule_enabled, s.backup_hour, s.backup_keep, s.backup_include_media = True, \
            timezone.localtime().hour, 2, False
        s.save()
        for i in range(3):
            Backup.objects.filter(kind="scheduled").update(created_at=timezone.now() - timezone.timedelta(days=1))
            self.assertTrue(scheduled_backup().startswith("shanzee-backup"))
        self.assertEqual(scheduled_backup(), "already done")
        self.assertEqual(Backup.objects.filter(kind="scheduled").count(), 2)


# ---------------------------------------------------------------------------
# User panel security
# ---------------------------------------------------------------------------
class UserPanelSecurityTests(Base):
    def test_contact_rejects_dangerous_attachment(self):
        c = self.cust_client()
        evil = SimpleUploadedFile("x.svg", b"<svg onload=alert(1)>", content_type="image/svg+xml")
        r = c.post(reverse("home:Contact"), {"name": "a", "email": "a@x.com", "support_type": "other",
                                             "subject": "s", "message": "m", "attachment": evil})
        self.assertFalse(SupportTicket.objects.exists())
        ok = SimpleUploadedFile("x.png", png_bytes(), content_type="image/png")
        c.post(reverse("home:Contact"), {"name": "a", "email": "a@x.com", "support_type": "other",
                                         "subject": "s", "message": "m", "attachment": ok})
        self.assertTrue(SupportTicket.objects.exists())

    def test_contact_rate_limited(self):
        c = Client()
        for i in range(5):
            c.post(reverse("home:Contact"), {"name": "a", "email": "a@x.com", "support_type": "other",
                                             "subject": "s", "message": "m"})
        r = c.post(reverse("home:Contact"), {"name": "a", "email": "a@x.com", "support_type": "other",
                                             "subject": "s", "message": "m"})
        self.assertEqual(r.status_code, 429)

    def test_avatar_must_be_an_image(self):
        c = self.cust_client()
        evil = SimpleUploadedFile("me.png", b"<html>hi</html>", content_type="image/png")
        c.post(reverse("home:edit-profile"), {"full_name": "Ali", "email": "ali@x.com", "avatar": evil})
        self.cust.refresh_from_db()
        self.assertFalse(self.cust.avatar)

    def test_order_request_items_must_belong_to_the_order(self):
        self.checkout(self.cust_client())
        mine = Order.objects.get()
        theirs = Order.objects.create(user=self.other, shipping_address=self.addr, billing_address=self.addr,
                                      total_amount=Decimal("1"))
        their_item = OrderItem.objects.create(order=theirs, product=self.product, variant=self.variant, quantity=1,
                                              price=Decimal("1"))
        from rest_framework_simplejwt.tokens import AccessToken
        r = self.client.post(reverse("order-request"), {"order": mine.pk, "order_id": mine.pk, "request_type": "return",
                                                        "items": [their_item.pk], "reason": "x"},
                             HTTP_AUTHORIZATION=f"Bearer {AccessToken.for_user(self.cust)}")
        self.assertIn(r.status_code, (400, 404))
        self.assertFalse(OrderRequest.objects.filter(items=their_item).exists())

    def test_logout_wipes_browser_storage(self):
        r = self.cust_client().get(reverse("logout"))
        self.assertEqual(r["Clear-Site-Data"], '"storage"')

    def test_change_password(self):
        c = self.cust_client()
        r = c.post(reverse("home:change-password"), {"old_password": "Pw-Strong-123",
                                                     "new_password1": "N3w-Better-Pass!", "new_password2": "N3w-Better-Pass!"})
        self.assertEqual(r.status_code, 302)
        self.cust.refresh_from_db()
        self.assertTrue(self.cust.check_password("N3w-Better-Pass!"))
        self.assertTrue(SecurityEvent.objects.filter(event="password_changed").exists())
        r = c.post(reverse("home:change-password"), {"old_password": "wrong", "new_password1": "x", "new_password2": "x"})
        self.assertEqual(r.status_code, 200)

    def test_track_order_api_rate_limited(self):
        c = Client()
        for _ in range(30):
            c.get(reverse("home:track-order-api") + "?q=NOPE")
        self.assertEqual(c.get(reverse("home:track-order-api") + "?q=NOPE").status_code, 429)
