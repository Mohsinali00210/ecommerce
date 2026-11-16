"""
Courier integration + security tests. Leopards HTTP calls are mocked.

Run:  python manage.py test couriers
"""
import json
from decimal import Decimal
from unittest import mock

from django.db import connection
from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.models import Address, User
from products.models import Product, ProductVariant
from Web.models import Cart, CartItem, Notification, Order, OrderItem

from couriers.adapters.base import CourierError
from couriers.models import (CourierCity, CourierCredential, CourierProvider, Shipment,
                             ShipmentEvent, ShipmentStatus, ShipperProfile, WebhookLog)
from couriers import services


def fake_response(payload, status=200):
    r = mock.Mock()
    r.status_code = status
    r.json.return_value = payload
    r.text = json.dumps(payload)
    return r


class Fixtures:
    def make_world(self):
        # The storefront header renders a Google login link, which needs a SocialApp row.
        from allauth.socialaccount.models import SocialApp
        SocialApp.objects.create(provider="google", name="Google", client_id="x", secret="y")
        self.leopards = CourierProvider.objects.get(code="leopards")  # seeded by migration
        self.cred = CourierCredential.objects.create(provider=self.leopards, environment="sandbox",
                                                     api_key="KEY-1234", api_password="PASS-9876")
        self.lahore = CourierCity.objects.create(provider=self.leopards, external_id="789", name="Lahore")
        self.karachi = CourierCity.objects.create(provider=self.leopards, external_id="475", name="Karachi",
                                                  aliases="Khi, Karachi City")
        self.shipper = ShipperProfile.objects.create(
            contact_name="Shan Zee Store", phone="03001112222", email="store@shanzee.com",
            address="12 Mall Road", city="Lahore", return_same_as_pickup=False,
            return_contact_name="Returns Desk", return_phone="03003334444",
            return_address="Plot 9, Returns Warehouse", return_city="Karachi", is_default=True)
        self.staff = User.objects.create_user(email="staff@x.com", password="pw-Strong-123",
                                              full_name="Staff", is_staff=True)
        from django.contrib.auth.models import Group
        self.staff.groups.add(Group.objects.get(name="Administrator"))  # RBAC role
        self.customer = User.objects.create_user(email="cust@x.com", password="pw-Strong-123",
                                                 full_name="Ali Khan")
        self.other = User.objects.create_user(email="other@x.com", password="pw-Strong-123",
                                              full_name="Other")
        self.product = Product.objects.create(name="Lawn Suit", sku="LS-1", price=Decimal("2500"),
                                              weight=Decimal("0.75"), stock_quantity=10)
        self.variant = ProductVariant.objects.create(product=self.product, name="Red / M", sku="LS-1-RM",
                                                     price=Decimal("2500"), stock_quantity=10)

    def make_order(self, user=None, city="karachi", qty=2, payment="cod"):
        user = user or self.customer
        addr = Address.objects.create(user=user, full_name=user.full_name, phone="03211234567",
                                      street_address="House 5, Block B", city=city,
                                      postal_code="75000")
        order = Order.objects.create(user=user, shipping_address=addr, billing_address=addr,
                                     payment_method=payment, status="pending",
                                     total_amount=Decimal("5150"), subtotal=Decimal("5000"))
        OrderItem.objects.create(order=order, product=self.product, variant=self.variant,
                                 quantity=qty, price=Decimal("2500"))
        return order


BOOK_OK = {"status": 1, "error": 0, "track_number": "LE7512345678",
           "slip_link": "https://merchantapistaging.leopardscourier.com/slip/LE7512345678"}


@override_settings(CELERY_TASK_ALWAYS_EAGER=True)
class BookingTests(Fixtures, TestCase):
    def setUp(self):
        self.make_world()

    def test_credentials_encrypted_at_rest(self):
        with connection.cursor() as c:
            c.execute("SELECT api_key, api_password FROM couriers_couriercredential WHERE id=%s",
                      [self.cred.pk])
            raw_key, raw_pw = c.fetchone()
        self.assertTrue(raw_key.startswith("enc$"))
        self.assertNotIn("KEY-1234", raw_key)
        self.assertNotIn("PASS-9876", raw_pw)
        self.assertEqual(CourierCredential.objects.get(pk=self.cred.pk).api_key, "KEY-1234")

    def test_city_alias_resolution(self):
        self.assertEqual(CourierCity.resolve(self.leopards, " KHI "), self.karachi)
        self.assertEqual(CourierCity.resolve(self.leopards, "lahore"), self.lahore)
        self.assertIsNone(CourierCity.resolve(self.leopards, "Atlantis"))

    @mock.patch("couriers.adapters.base.requests.request")
    def test_book_sends_customer_return_weight_and_description(self, req):
        req.return_value = fake_response(BOOK_OK)
        order = self.make_order()
        shipment = services.book_order_with_defaults(order, user=self.staff)

        method, url = req.call_args.args
        body = req.call_args.kwargs["json"]
        self.assertEqual(method, "POST")
        self.assertEqual(url, "https://merchantapistaging.leopardscourier.com/api/bookPacket/format/json/")
        self.assertEqual(body["api_key"], "KEY-1234")
        self.assertEqual(body["booked_packet_weight"], 1500)          # 0.75kg x 2
        self.assertEqual(body["booked_packet_collect_amount"], 5150)  # COD = order total
        self.assertEqual(body["destination_city"], "475")             # Karachi
        self.assertEqual(body["origin_city"], "789")                  # shipper in Lahore
        self.assertEqual(body["consignment_name_eng"], "Ali Khan")
        self.assertEqual(body["consignment_phone"], "03211234567")
        self.assertIn("House 5", body["consignment_address"])
        self.assertEqual(body["shipment_name_eng"], "Shan Zee Store")
        self.assertEqual(body["return_address"], "Plot 9, Returns Warehouse")
        self.assertEqual(body["return_city"], "475")
        self.assertIn("2x Lawn Suit (Red / M)", body["custom_data"][0]["description"])
        self.assertEqual(body["booked_packet_order_id"], order.order_number)

        self.assertEqual(shipment.tracking_number, "LE7512345678")
        self.assertEqual(shipment.status, ShipmentStatus.BOOKED)
        stored = json.dumps(shipment.request_payload)                  # secrets never stored
        self.assertNotIn("KEY-1234", stored)
        self.assertNotIn("PASS-9876", stored)
        order.refresh_from_db()
        self.assertEqual(order.tracking_number, "LE7512345678")
        self.assertEqual(order.status, "booked")
        self.assertTrue(Notification.objects.filter(order=order, notification_type="order_dispatched").exists())

    @mock.patch("couriers.adapters.base.requests.request")
    def test_prepaid_order_has_zero_cod(self, req):
        req.return_value = fake_response(BOOK_OK)
        order = self.make_order(payment="card")
        services.book_order_with_defaults(order)
        self.assertEqual(req.call_args.kwargs["json"]["booked_packet_collect_amount"], 0)

    @mock.patch("couriers.adapters.base.requests.request")
    def test_failed_booking_is_recorded_and_can_retry(self, req):
        req.return_value = fake_response({"status": 0, "error": "Invalid destination city"})
        order = self.make_order()
        with self.assertRaisesMessage(CourierError, "Invalid destination city"):
            services.book_order_with_defaults(order)
        failed = Shipment.objects.get(order=order)
        self.assertEqual(failed.status, ShipmentStatus.BOOKING_FAILED)
        # a failed attempt doesn't block re-booking
        req.return_value = fake_response(BOOK_OK)
        ok = services.book_order_with_defaults(order)
        self.assertEqual(ok.status, ShipmentStatus.BOOKED)

    @mock.patch("couriers.adapters.base.requests.request")
    def test_cannot_double_book(self, req):
        req.return_value = fake_response(BOOK_OK)
        order = self.make_order()
        services.book_order_with_defaults(order)
        with self.assertRaisesMessage(CourierError, "already booked"):
            services.book_order_with_defaults(order)
        self.assertEqual(req.call_count, 1)

    def test_unknown_city_blocks_auto_booking(self):
        order = self.make_order(city="Atlantis")
        with self.assertRaisesMessage(CourierError, "could not be matched"):
            services.book_order_with_defaults(order)

    @mock.patch("couriers.adapters.base.requests.request")
    def test_cancel(self, req):
        req.return_value = fake_response(BOOK_OK)
        order = self.make_order()
        s = services.book_order_with_defaults(order)
        req.return_value = fake_response({"status": 1, "error": 0})
        services.cancel_shipment(s, user=self.staff)
        self.assertEqual(req.call_args.args[1].split("/api/")[1], "cancelBookedPackets/format/json/")
        self.assertEqual(req.call_args.kwargs["json"]["cn_numbers"], "LE7512345678")
        s.refresh_from_db(); order.refresh_from_db()
        self.assertEqual(s.status, ShipmentStatus.CANCELLED)
        self.assertIsNone(order.tracking_number)
        self.assertEqual(order.status, "processing")


def track_payload(status, details):
    return {"status": 1, "error": 0, "packet_list": [{
        "track_number": "LE7512345678", "booked_packet_status": status,
        "Tracking Detail": [{"Status": s, "Activity_datetime": t, "Reason": r} for s, t, r in details],
    }]}


@override_settings(CELERY_TASK_ALWAYS_EAGER=True)
class TrackingTests(Fixtures, TestCase):
    def setUp(self):
        self.make_world()
        with mock.patch("couriers.adapters.base.requests.request", return_value=fake_response(BOOK_OK)):
            self.order = self.make_order()
            self.shipment = services.book_order_with_defaults(self.order)

    @mock.patch("couriers.adapters.base.requests.request")
    def test_poll_moves_shipment_and_order_to_delivered(self, req):
        req.return_value = fake_response(track_payload("Delivered", [
            ("Shipment Picked", "2026-11-10 10:00:00", ""),
            ("Arrived at Station", "2026-11-11 08:00:00", "Karachi"),
            ("Assigned to Courier", "2026-11-11 09:30:00", ""),
            ("Delivered", "2026-11-11 15:10:00", "Received by Ali"),
        ]))
        from couriers.tasks import poll_active_shipments
        res = poll_active_shipments()
        self.assertEqual(res["changed"], 1)
        self.shipment.refresh_from_db(); self.order.refresh_from_db()
        self.assertEqual(self.shipment.status, ShipmentStatus.DELIVERED)
        self.assertEqual(self.order.status, "delivered")
        self.assertIsNotNone(self.order.delivered_at)
        n_events = self.shipment.events.count()
        self.assertGreaterEqual(n_events, 5)  # booked + 4 scans
        # polling again does not duplicate events or re-open a delivered shipment
        services.refresh_shipments([self.shipment])
        self.assertEqual(self.shipment.events.count(), n_events)
        self.assertTrue(Notification.objects.filter(order=self.order, notification_type="order_delivered").exists())

    @mock.patch("couriers.adapters.base.requests.request")
    def test_undelivered_is_not_delivered(self, req):
        req.return_value = fake_response(track_payload("Undelivered", [("Undelivered", "2026-11-11 12:00", "Refused")]))
        services.refresh_shipments([self.shipment])
        self.shipment.refresh_from_db(); self.order.refresh_from_db()
        self.assertEqual(self.shipment.status, ShipmentStatus.DELIVERY_FAILED)
        self.assertEqual(self.order.status, "booked")  # order untouched

    @mock.patch("couriers.adapters.base.requests.request")
    def test_returned_to_shipper_restocks(self, req):
        self.variant.refresh_from_db()
        before = self.variant.stock_quantity
        req.return_value = fake_response(track_payload("Returned to shipper", []))
        services.refresh_shipments([self.shipment])
        self.order.refresh_from_db(); self.variant.refresh_from_db()
        self.assertEqual(self.order.status, "returned")
        self.assertEqual(self.variant.stock_quantity, before + 2)

    @mock.patch("couriers.adapters.base.requests.request")
    def test_unmapped_status_is_flagged(self, req):
        req.return_value = fake_response(track_payload("Held at customs desk", []))
        services.refresh_shipments([self.shipment])
        self.shipment.refresh_from_db()
        self.assertTrue(self.shipment.unmapped_status)
        self.assertEqual(self.shipment.status, ShipmentStatus.BOOKED)

    @mock.patch("couriers.adapters.base.requests.request")
    def test_tracking_errors_are_counted(self, req):
        req.return_value = fake_response({"status": 0, "error": "Invalid API key"})
        services.refresh_shipments([self.shipment])
        self.shipment.refresh_from_db()
        self.assertEqual(self.shipment.tracking_failures, 1)
        self.assertIn("Invalid API key", self.shipment.error_message)

    def test_webhook_rejects_bad_token(self):
        url = reverse("couriers_public:webhook", args=["leopards", "wrong-token"])
        r = self.client.post(url, data=json.dumps({"track_number": "LE7512345678", "status": "Delivered"}),
                             content_type="application/json")
        self.assertEqual(r.status_code, 401)
        self.shipment.refresh_from_db()
        self.assertEqual(self.shipment.status, ShipmentStatus.BOOKED)
        self.assertFalse(WebhookLog.objects.get().authenticated)

    def test_webhook_updates_status(self):
        url = reverse("couriers_public:webhook", args=["leopards", self.cred.webhook_token])
        with self.captureOnCommitCallbacks(execute=True):
            r = self.client.post(url, data=json.dumps({
                "track_number": "LE7512345678", "status": "Out for Delivery",
                "activity_datetime": "2026-11-12 09:00:00"}), content_type="application/json")
        self.assertEqual(r.status_code, 200)
        self.shipment.refresh_from_db(); self.order.refresh_from_db()
        self.assertEqual(self.shipment.status, ShipmentStatus.OUT_FOR_DELIVERY)
        self.assertEqual(self.order.status, "out_for_delivery")
        wl = WebhookLog.objects.get()
        self.assertTrue(wl.success)
        self.assertEqual(wl.updates_applied, 1)
        self.assertTrue(self.shipment.events.filter(source="webhook").exists())

    def test_webhook_form_encoded_list(self):
        url = reverse("couriers_public:webhook", args=["leopards", self.cred.webhook_token])
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(url, data={"cn_number": "LE7512345678", "booked_packet_status": "Delivered"})
        self.shipment.refresh_from_db()
        self.assertEqual(self.shipment.status, ShipmentStatus.DELIVERED)

    def test_customer_tracking_only_own_order(self):
        url = reverse("couriers_public:customer_tracking", args=[self.order.order_number])
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(url).status_code, 404)
        self.client.force_login(self.customer)
        data = self.client.get(url).json()
        self.assertEqual(data["shipment"]["tracking_number"], "LE7512345678")


@override_settings(CELERY_TASK_ALWAYS_EAGER=True)
class AutoBookTests(Fixtures, TestCase):
    def setUp(self):
        self.make_world()
        self.leopards.auto_book_enabled = True
        self.leopards.save()

    @mock.patch("couriers.adapters.base.requests.request")
    def test_order_to_processing_auto_books(self, req):
        req.return_value = fake_response(BOOK_OK)
        order = self.make_order()
        with self.captureOnCommitCallbacks(execute=True):
            order.status = "processing"
            order.save()
        s = Shipment.objects.get(order=order)
        self.assertTrue(s.auto_booked)
        self.assertEqual(s.tracking_number, "LE7512345678")

    @mock.patch("couriers.adapters.base.requests.request")
    def test_non_cod_not_auto_booked_by_default(self, req):
        order = self.make_order(payment="card")
        with self.captureOnCommitCallbacks(execute=True):
            order.status = "processing"
            order.save()
        self.assertFalse(Shipment.objects.filter(order=order).exists())
        req.assert_not_called()


class AdminScreenTests(Fixtures, TestCase):
    def setUp(self):
        self.make_world()
        self.order = self.make_order()

    def test_customer_cannot_open_courier_admin(self):
        self.client.force_login(self.customer)
        for name, args in [("couriers:dashboard", []), ("couriers:settings", []),
                           ("couriers:book", [self.order.pk])]:
            r = self.client.get(reverse(name, args=args))
            self.assertEqual(r.status_code, 403, name)  # signed in, but not staff

    def test_staff_pages_render(self):
        self.client.force_login(self.staff)
        for name, args in [("couriers:dashboard", []), ("couriers:settings", []),
                           ("couriers:book", [self.order.pk]), ("couriers:provider_add", []),
                           ("couriers:shipper_add", []), ("couriers:mapping_add", []),
                           ("couriers:credential_add", [self.leopards.pk])]:
            r = self.client.get(reverse(name, args=args))
            self.assertEqual(r.status_code, 200, name)
        r = self.client.get(reverse("couriers:book", args=[self.order.pk]))
        self.assertContains(r, "Karachi")
        self.assertNotContains(r, "PASS-9876")
        r = self.client.get(reverse("couriers:settings"))
        self.assertNotContains(r, "KEY-1234")
        self.assertContains(r, "1234")  # masked: ••••••1234

    @mock.patch("couriers.adapters.base.requests.request")
    def test_book_form_post(self, req):
        req.return_value = fake_response(BOOK_OK)
        self.client.force_login(self.staff)
        r = self.client.post(reverse("couriers:book", args=[self.order.pk]), {
            "provider": self.leopards.pk, "shipper": self.shipper.pk, "weight_grams": 900, "pieces": 2,
            "description": "2 lawn suits", "cod_amount": "5150", "consignee_name": "Ali Khan",
            "consignee_phone": "03211234567", "consignee_address": "House 5",
            "destination_city": self.karachi.pk, "destination_city_name": "karachi"})
        s = Shipment.objects.get(order=self.order)
        self.assertRedirects(r, reverse("couriers:shipment", args=[s.pk]))
        body = req.call_args.kwargs["json"]
        self.assertEqual(body["booked_packet_weight"], 900)
        self.assertEqual(body["booked_packet_no_piece"], 2)
        r = self.client.get(reverse("couriers:shipment", args=[s.pk]))
        self.assertContains(r, "LE7512345678")

    def test_credential_edit_keeps_secret_when_blank(self):
        self.client.force_login(self.staff)
        self.client.post(reverse("couriers:credential_edit", args=[self.leopards.pk, self.cred.pk]), {
            "label": "Main", "environment": "sandbox", "api_key": "", "api_password": "",
            "account_number": "", "extra": "{}", "extra_secret": "", "is_active": "on"})
        self.cred.refresh_from_db()
        self.assertEqual(self.cred.api_key, "KEY-1234")
        self.assertEqual(self.cred.label, "Main")


class SecurityFixTests(Fixtures, TestCase):
    def setUp(self):
        self.make_world()

    def test_customer_cannot_use_product_admin(self):
        self.client.force_login(self.customer)
        r = self.client.get(reverse("product_edit", args=[self.product.pk]))
        self.assertEqual(r.status_code, 403)
        r = self.client.post(reverse("variant_delete", args=[self.product.pk, self.variant.pk]))
        self.assertEqual(r.status_code, 403)
        self.variant.refresh_from_db()
        self.assertFalse(self.variant.is_deleted)

    def test_delete_requires_post_for_staff(self):
        self.client.force_login(self.staff)
        r = self.client.get(reverse("image_delete", args=[self.product.pk, 1]))
        self.assertEqual(r.status_code, 405)

    def test_reports_staff_only(self):
        self.client.force_login(self.customer)
        self.assertEqual(self.client.get(reverse("sales_report")).status_code, 403)
        from rest_framework_simplejwt.tokens import RefreshToken
        token = str(RefreshToken.for_user(self.customer).access_token)
        r = self.client.get("/Adminpanel/Reports/get-sales-report/", HTTP_AUTHORIZATION=f"Bearer {token}")
        self.assertEqual(r.status_code, 403)

    def test_user_api_staff_only(self):
        from rest_framework_simplejwt.tokens import RefreshToken
        token = str(RefreshToken.for_user(self.customer).access_token)
        r = self.client.get("/api/v1/users/", HTTP_AUTHORIZATION=f"Bearer {token}")
        self.assertEqual(r.status_code, 403)
        r = self.client.post(f"/api/v1/users/{self.other.pk}/block/", HTTP_AUTHORIZATION=f"Bearer {token}")
        self.assertEqual(r.status_code, 403)
        self.other.refresh_from_db()
        self.assertTrue(self.other.is_active)

    def _jwt(self, user):
        from rest_framework_simplejwt.tokens import RefreshToken
        return {"HTTP_AUTHORIZATION": f"Bearer {RefreshToken.for_user(user).access_token}"}

    def test_order_detail_only_own(self):
        order = self.make_order(user=self.other)
        r = self.client.get(reverse("OrderDetailApi", args=[order.pk]), **self._jwt(self.customer))
        self.assertEqual(r.status_code, 404)
        r = self.client.get(reverse("OrderDetailApi", args=[order.pk]), **self._jwt(self.other))
        self.assertEqual(r.status_code, 200)

    def test_order_request_only_own(self):
        order = self.make_order(user=self.other)
        r = self.client.post(reverse("order-request"), {"order_id": order.pk, "request_type": "cancel",
                                                        "reason": "x"}, **self._jwt(self.customer))
        self.assertEqual(r.status_code, 404)

    def test_cannot_remove_someone_elses_cart_item(self):
        cart = Cart.objects.create(user=self.other)
        item = CartItem.objects.create(cart=cart, product=self.product, variant=self.variant,
                                       quantity=1, price=Decimal("2500"))
        self.client.force_login(self.customer)
        r = self.client.post(reverse("RemoveCartItem"), {"item_id": item.pk})
        self.assertEqual(r.status_code, 404)
        item.refresh_from_db()
        self.assertFalse(item.is_deleted)

    def test_stock_cannot_go_negative(self):
        from django.core.exceptions import ValidationError
        order = self.make_order(qty=10)  # takes all 10
        self.variant.refresh_from_db()
        self.assertEqual(self.variant.stock_quantity, 0)
        with self.assertRaises(ValidationError):
            OrderItem.objects.create(order=order, product=self.product, variant=self.variant,
                                     quantity=1, price=Decimal("2500"))
        self.product.refresh_from_db()
        self.assertEqual(self.product.sold, 10)

    def test_cancel_restores_stock(self):
        order = self.make_order(qty=3)
        order.status = "cancelled"
        order.save()
        self.variant.refresh_from_db(); self.product.refresh_from_db()
        self.assertEqual(self.variant.stock_quantity, 10)
        self.assertEqual(self.product.sold, 0)

    def test_send_message_requires_login_csrf_and_creates_thread(self):
        from django.test import Client
        url = reverse("send_message")
        payload = json.dumps({"message": "hi", "product_id": self.product.pk})
        r = self.client.post(url, data=payload, content_type="application/json")
        self.assertEqual(r.status_code, 302)  # login required now
        strict = Client(enforce_csrf_checks=True)
        strict.force_login(self.customer)
        r = strict.post(url, data=payload, content_type="application/json")
        self.assertEqual(r.status_code, 403)  # csrf_exempt removed
        self.client.force_login(self.customer)
        r = self.client.post(url, data=payload, content_type="application/json")
        self.assertEqual(r.status_code, 200)  # first message no longer crashes
        self.assertTrue(r.json()["success"])

    def test_otp_lockout_after_five_wrong_codes(self):
        from accounts.utils import generate_otp
        otp = generate_otp(self.customer, "RESET_PASSWORD")
        session = self.client.session
        session["reset_email"] = self.customer.email
        session.save()
        wrong = "000000" if otp.code != "000000" else "111111"
        for _ in range(5):
            self.client.post(reverse("reset-password"), {"code": wrong, "password1": "NewPass-123",
                                                         "password2": "NewPass-123"})
        r = self.client.post(reverse("reset-password"), {"code": otp.code, "password1": "NewPass-123",
                                                         "password2": "NewPass-123"})
        self.assertContains(r, "Too many wrong codes")
        self.customer.refresh_from_db()
        self.assertFalse(self.customer.check_password("NewPass-123"))


@override_settings(CELERY_TASK_ALWAYS_EAGER=True)
class ExistingPagesSmokeTests(Fixtures, TestCase):
    """Pages that were edited for the integration still render."""

    def setUp(self):
        self.make_world()

    def test_admin_order_pages_have_courier_button(self):
        admin = User.objects.create_superuser(email="root@x.com", password="pw-Strong-123")
        self.client.force_login(admin)
        for url in [reverse("Orders"), reverse("OrdersByStatus", args=["processing"])]:
            r = self.client.get(url)
            self.assertEqual(r.status_code, 200, url)
            self.assertContains(r, "courierBookBase")
        r = self.client.get(reverse("product_edit", args=[self.product.pk]))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "postLinkForm")

    @mock.patch("couriers.adapters.base.requests.request")
    def test_public_track_order_shows_courier(self, req):
        req.return_value = fake_response(BOOK_OK)
        order = self.make_order()
        services.book_order_with_defaults(order)
        r = self.client.get(reverse("home:track-order-api") + f"?q={order.order_number}")
        self.assertEqual(r.status_code, 200)
        data = r.json()["order"]
        self.assertEqual(data["courier"]["tracking_number"], "LE7512345678")
        self.assertIsNone(data["shipping_address"])  # anonymous: no address
        self.assertEqual(self.client.get(reverse("home:track-order")).status_code, 200)

    def test_city_list_api(self):
        r = self.client.get(reverse("couriers_public:city_list"))
        self.assertEqual(r.json()["cities"], ["Karachi", "Lahore"])

    def test_addresses_page_has_city_suggestions(self):
        self.client.force_login(self.customer)
        r = self.client.get(reverse("home:user-address"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "courierCities")


# Orders generate QR images on save - keep test files out of the real media folder.
import tempfile as _tempfile  # noqa: E402

_TEST_MEDIA = _tempfile.mkdtemp(prefix="shanzee-test-media-")
for _name, _obj in list(globals().items()):
    if isinstance(_obj, type) and issubclass(_obj, TestCase) and _obj is not TestCase:
        globals()[_name] = override_settings(MEDIA_ROOT=_TEST_MEDIA)(_obj)
