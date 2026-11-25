"""
Weight-based shipping (Leopards Overnight tariff), multiple payment gateways, the sandbox test
gateway, wallet payouts with charges, payment/payout logs, transaction history, the Google
Merchant API and the mobile logout link.

Run:  python manage.py test payments.tests.test_shipping_gateways_payouts
"""
import hashlib
import hmac
import json
import time
from decimal import Decimal
from unittest import mock

from django.test import Client, override_settings
from django.urls import reverse

from accounts.models import Address
from adminpanel import shipping
from couriers.models import ShippingTariff, ShippingZone
from couriers.tariffs import charge, province_of, zone_for
from payments.models import Payment, PaymentEvent, PaymentGateway, PayoutEvent, PayoutMethod
from Web.models import Order, UserWallet, WithdrawalRequest

from .test_orders_payments import Base as _Base


@override_settings(SECURE_SSL_REDIRECT=False)  # a local .env with debug off turns the HTTPS redirect on
class Base(_Base):
    pass

D = Decimal


class TariffBase(Base):
    def setUp(self):
        super().setUp()
        self.tariff = ShippingTariff.objects.get(is_default=True)
        self.tariff.origin_city, self.tariff.origin_province = "Lahore", "Punjab"
        self.tariff.save()
        self.store.free_shipping_enabled = False
        self.store.weight_shipping_enabled = True
        self.store.max_shipping_charge = D("0")
        self.store.save()


# ---------------------------------------------------------------------------
# Weight-based shipping
# ---------------------------------------------------------------------------
class TariffTests(TariffBase):
    def test_seeded_leopards_overnight_rates(self):
        t = self.tariff
        self.assertEqual(t.name, "Leopards Overnight - COD")
        self.assertEqual(t.provider.code, "leopards")
        rows = [(s.max_grams, s.within_city, s.same_province, s.other_province) for s in t.slabs.all()]
        self.assertEqual(rows, [(250, D("160"), D("180"), D("200")), (500, D("180"), D("200"), D("230")),
                                (1000, D("180"), D("230"), D("250"))])

    def test_charge_by_slab_and_zone(self):
        t = self.tariff
        self.assertEqual(charge(t, 200, ShippingZone.WITHIN_CITY), D("160"))
        self.assertEqual(charge(t, 250, ShippingZone.SAME_PROVINCE), D("180"))   # inclusive upper limit
        self.assertEqual(charge(t, 251, ShippingZone.SAME_PROVINCE), D("200"))
        self.assertEqual(charge(t, 800, ShippingZone.OTHER_PROVINCE), D("250"))
        self.assertEqual(charge(t, 800, None), D("250"))                          # unknown zone -> Zone B
        t.extra_other_province = D("50")
        t.save()
        self.assertEqual(charge(t, 1600, ShippingZone.OTHER_PROVINCE), D("350"))  # 1 kg + 2 started steps

    def test_zones(self):
        t = self.tariff
        self.assertEqual(zone_for(t, "lahore"), ShippingZone.WITHIN_CITY)
        self.assertEqual(zone_for(t, "Multan"), ShippingZone.SAME_PROVINCE)
        self.assertEqual(zone_for(t, "Karachi"), ShippingZone.OTHER_PROVINCE)
        self.assertEqual(zone_for(t, "Some Village", "Punjab"), ShippingZone.SAME_PROVINCE)
        self.assertEqual(zone_for(t, "Some Village"), ShippingZone.OTHER_PROVINCE)
        self.assertEqual(province_of("Peshawar"), "khyber pakhtunkhwa")
        self.assertEqual(province_of("X", "KPK"), "khyber pakhtunkhwa")

    def _set_weight(self, kg, **kw):
        # .update(): Product.save() would also re-sync the fixture's variants
        type(self.product).objects.filter(pk=self.product.pk).update(weight=D(kg), **kw)
        self.product.refresh_from_db()

    def test_order_charges_weight_for_the_address_zone(self):
        self._set_weight("0.30", shipping_charges=D("99"))           # 300 g, Lahore -> within city
        r = self.checkout(self.cust_client())
        self.assertEqual(r.status_code, 201, r.content)
        o = Order.objects.get()
        self.assertEqual(o.shipping_charges, D("180"))
        self.assertEqual(o.total_amount, D("2680"))

    def test_quantity_adds_weight_to_one_parcel(self):
        self._set_weight("0.30")
        self.addr.city = "Karachi"
        self.addr.save()
        self.checkout(self.cust_client(), qty=2)                       # 600 g to Zone B
        self.assertEqual(Order.objects.get().shipping_charges, D("250"))

    def test_free_shipping_item_and_threshold_and_switch(self):
        self._set_weight("0.30", free_shipping=True)
        self.checkout(self.cust_client())
        self.assertEqual(Order.objects.get().shipping_charges, D("0"))
        Order.objects.all().delete()
        self._set_weight("0.30", free_shipping=False, shipping_charges=D("99"))
        self.store.weight_shipping_enabled = False
        self.store.save()
        self.checkout(self.cust_client())
        self.assertEqual(Order.objects.get().shipping_charges, D("99"))  # flat charge when switched off
        Order.objects.all().delete()
        self.store.weight_shipping_enabled = True
        self.store.free_shipping_enabled, self.store.free_shipping_threshold = True, D("2000")
        self.store.save()
        self.checkout(self.cust_client())
        self.assertEqual(Order.objects.get().shipping_charges, D("0"))   # over the threshold

    def test_checkout_quote_and_page(self):
        self._set_weight("0.30")
        c = self.cust_client()
        self.session_items(c)
        self.addr.is_default = True
        self.addr.save()
        page = c.get(reverse("home:MyCheckoutPage"))
        self.assertContains(page, 'id="coShippingZone"')
        self.assertContains(page, "Within city")
        q = c.get(reverse("home:checkout-shipping-quote"), {"city": "Quetta"}).json()
        self.assertEqual(q["shipping_total"], 230.0)
        self.assertEqual(q["shipping_zone_label"], ShippingZone.OTHER_PROVINCE.label)
        q = c.get(reverse("home:checkout-shipping-quote"), {"address_id": self.addr.pk}).json()
        self.assertEqual(q["shipping_total"], 180.0)

    def test_cart_page_has_tariff_for_js(self):
        self._set_weight("0.30")
        c = self.cust_client()
        self.session_items(c)
        r = c.get(reverse("home:MyCart"))
        self.assertContains(r, "summaryWeightRow")
        self.assertContains(r, '"slabs": [[250, 160.0], [500, 180.0], [1000, 180.0]]')  # Lahore address

    def test_product_note_lists_zone_rates(self):
        self._set_weight("0.30")
        note = shipping.product_note(self.product, D("2500"), self.addr)
        self.assertEqual([r["price"] for r in note["weight"]["rows"]], [D("180"), D("200"), D("230")])
        self.assertEqual(note["weight"]["yours"], D("180"))
        self.assertEqual(shipping.product_shipping_price(self.product, D("2500")), D("230"))  # feeds: highest

    def test_admin_rates_page_and_edit(self):
        admin = Client()
        admin.force_login(self.root)
        r = admin.get(reverse("couriers:tariffs"), {"grams": "300", "city": "Multan"})
        self.assertContains(r, "Leopards Overnight - COD")
        self.assertContains(r, "Rs 200.00")                           # Multan = Zone A, 300 g
        t = self.tariff
        slabs = list(t.slabs.all())
        data = {"name": t.name, "provider": t.provider_id, "service_type": "overnight", "origin_city": "Lahore",
                "origin_province": "punjab", "is_active": "on", "is_default": "on", "extra_step_grams": "500",
                "extra_within_city": "20", "extra_same_province": "30", "extra_other_province": "40", "notes": "",
                "slabs-TOTAL_FORMS": str(len(slabs) + 1), "slabs-INITIAL_FORMS": str(len(slabs)),
                "slabs-MIN_NUM_FORMS": "0", "slabs-MAX_NUM_FORMS": "1000"}
        for i, s in enumerate(slabs):
            data.update({f"slabs-{i}-id": s.pk, f"slabs-{i}-tariff": t.pk, f"slabs-{i}-max_grams": s.max_grams,
                         f"slabs-{i}-within_city": s.within_city, f"slabs-{i}-same_province": s.same_province,
                         f"slabs-{i}-other_province": s.other_province})
        n = len(slabs)
        data.update({f"slabs-{n}-max_grams": "2000", f"slabs-{n}-within_city": "250",
                     f"slabs-{n}-same_province": "300", f"slabs-{n}-other_province": "350"})
        r = admin.post(reverse("couriers:tariff_edit", args=[t.pk]), data)
        self.assertEqual(r.status_code, 302, r.content[:2000])
        t.refresh_from_db()
        self.assertEqual(t.origin_province, "Punjab")
        self.assertEqual(charge(t, 1500, ShippingZone.OTHER_PROVINCE), D("350"))


# ---------------------------------------------------------------------------
# Payment gateways
# ---------------------------------------------------------------------------
class GatewayTests(Base):
    def setUp(self):
        super().setUp()
        self.store.online_payments_enabled = True
        self.store.save()
        PaymentGateway.objects.filter(code="test").update(is_active=True)
        self.root_addr = Address.objects.create(user=self.root, full_name="Root", phone="0300", street_address="1",
                                                city="Lahore", postal_code="54000")

    def test_cod_is_default_and_test_gateway_staff_only(self):
        from payments.services import available_methods
        cust = available_methods(user=self.cust)
        self.assertEqual(cust[0]["value"], "cod")
        self.assertNotIn("online:test", [m["value"] for m in cust])
        self.assertIn("online:test", [m["value"] for m in available_methods(user=self.root)])
        r = self.checkout(self.cust_client(), method="online:test")
        self.assertEqual(r.status_code, 400)                            # refused on the server too

    def test_test_gateway_full_flow(self):
        c = self.cust_client(self.root)
        self.addr = self.root_addr
        r = self.checkout(c, method="online:test")
        self.assertEqual(r.status_code, 201, r.content)
        p = Payment.objects.get()
        self.assertEqual((p.method, p.gateway.code), ("online", "test"))
        r = c.get(r.json()["payment_url"])
        self.assertEqual(r.status_code, 302)
        page = c.get(r["Location"])
        self.assertContains(page, "Simulate successful payment")
        r = c.post(r["Location"], {"outcome": "paid"})
        self.assertContains(r, 'name="result"')
        result = r.context["fields"]["result"]
        c.post(reverse("payments:return", args=[p.pk]), {"result": result})
        p.refresh_from_db()
        self.assertEqual(p.status, "paid")
        self.assertEqual(p.order.payment_status, "paid")
        self.assertTrue(PaymentEvent.objects.filter(payment=p, kind="return_paid", verified=True).exists())

    def test_test_gateway_forged_result_is_ignored(self):
        c = self.cust_client(self.root)
        self.addr = self.root_addr
        self.checkout(c, method="online:test")
        p = Payment.objects.get()
        from Web.order_emails import order_token
        c.get(reverse("payments:pay", args=[order_token(p.order)]))
        c.post(reverse("payments:return", args=[p.pk]), {"result": "forged"})
        p.refresh_from_db()
        self.assertEqual(p.status, "pending")

    def _jazzcash(self):
        g = PaymentGateway.objects.get(code="jazzcash")
        g.api_key, g.secret_key, g.webhook_secret, g.is_active = "MC123", "salt-xyz", "pw", True
        g.save()
        return g

    def test_jazzcash_hash_and_return(self):
        from payments.gateways.jazzcash import secure_hash
        g = self._jazzcash()
        self.checkout(self.cust_client(), method="online:jazzcash")
        p = Payment.objects.get()
        session = g.adapter().start(p, "https://shop.test/r", "https://shop.test/c")
        f = session.post_fields
        self.assertEqual(f["pp_Amount"], "250000")                      # paisa
        self.assertEqual(f["pp_SecureHash"], secure_hash(f, "salt-xyz"))
        p.tracker = session.tracker
        p.save()
        back = {"pp_TxnRefNo": p.tracker, "pp_ResponseCode": "000", "pp_RetreivalReferenceNo": "RR1",
                "pp_Amount": "250000"}
        back["pp_SecureHash"] = secure_hash(back, "salt-xyz")
        res = g.adapter().handle_return(p, dict(back, pp_Amount="1"))   # tampered
        self.assertEqual(res.event, "pending")
        self.cust_client().post(reverse("payments:return", args=[p.pk]), back)
        p.refresh_from_db()
        self.assertEqual((p.status, p.reference), ("paid", "RR1"))

    def test_pay_page_auto_posts_for_form_gateways(self):
        from Web.order_emails import order_token
        self._jazzcash()
        self.checkout(self.cust_client(), method="online:jazzcash")
        p = Payment.objects.get()
        r = Client().get(reverse("payments:pay", args=[order_token(p.order)]))
        self.assertContains(r, 'action="https://sandbox.jazzcash.com.pk/CustomerPortal/')
        self.assertContains(r, 'name="pp_SecureHash"')

    def test_easypaisa_steps(self):
        from payments.gateways.easypaisa import hashed_request
        g = PaymentGateway.objects.get(code="easypaisa")
        g.api_key, g.secret_key, g.is_active = "1234", "0123456789ABCDEF", True
        g.save()
        self.assertEqual(hashed_request({"b": "2", "a": "1"}, "0123456789ABCDEF"),
                         hashed_request({"a": "1", "b": "2"}, "0123456789ABCDEF"))
        self.checkout(self.cust_client(), method="online:easypaisa")
        p = Payment.objects.get()
        s = g.adapter().start(p, "https://shop.test/r", "https://shop.test/c")
        self.assertIn("merchantHashedReq", s.post_fields)
        p.tracker = s.tracker
        p.save()
        self.assertEqual(g.adapter().handle_return(p, {"auth_token": "tok"}).event, "redirect")
        self.assertEqual(g.adapter().handle_return(p, {"status": "0001", "desc": "x"}).event, "failed")
        # an unsigned "success" is never trusted without the inquiry API
        self.assertEqual(g.adapter().handle_return(p, {"status": "0000", "orderRefNumber": p.tracker}).event,
                         "pending")

    def test_stripe_webhook_signature(self):
        g = PaymentGateway.objects.get(code="stripe")
        g.secret_key, g.webhook_secret, g.is_active = "sk_test_x", "whsec_abc", True
        g.save()
        self.checkout(self.cust_client(), method="online:stripe")
        p = Payment.objects.get()
        p.tracker = "cs_test_1"
        p.save()
        body = json.dumps({"id": "evt_1", "type": "checkout.session.completed",
                           "data": {"object": {"id": "cs_test_1", "payment_status": "paid",
                                               "payment_intent": "pi_1"}}}).encode()
        ts = str(int(time.time()))
        sig = hmac.new(b"whsec_abc", ts.encode() + b"." + body, hashlib.sha256).hexdigest()
        url = reverse("payments:webhook", args=["stripe"])
        bad = Client().post(url, body, content_type="application/json", HTTP_STRIPE_SIGNATURE=f"t={ts},v1=bad")
        self.assertEqual(bad.status_code, 400)
        ok = Client().post(url, body, content_type="application/json", HTTP_STRIPE_SIGNATURE=f"t={ts},v1={sig}")
        self.assertEqual(ok.status_code, 200)
        p.refresh_from_db()
        self.assertEqual((p.status, p.reference), ("paid", "pi_1"))

    def test_admin_gateway_pages_and_logs(self):
        admin = Client()
        admin.force_login(self.root)
        self.assertContains(admin.get(reverse("admin_payment_gateway")), "JazzCash")
        r = admin.get(reverse("admin_payment_gateway_edit", args=["jazzcash"]))
        self.assertContains(r, "Integrity salt")
        r = admin.post(reverse("admin_payment_gateway_edit", args=["jazzcash"]), {
            "name": "JazzCash", "checkout_label": "", "environment": "sandbox", "api_key": "MC1", "secret_key": "s",
            "webhook_secret": "p", "sandbox_base_url": "https://sandbox.jazzcash.com.pk",
            "live_base_url": "https://payments.jazzcash.com.pk", "sort_order": "20", "is_active": "on",
            "extra__txn_type": "MWALLET", "extra__bank_id": "", "extra__product_id": ""})
        self.assertEqual(r.status_code, 302)
        g = PaymentGateway.objects.get(code="jazzcash")
        self.assertTrue(g.configured)
        self.assertEqual(g.extra["txn_type"], "MWALLET")
        self.assertContains(admin.get(reverse("admin_payment_logs")), "gateway_settings_changed")


# ---------------------------------------------------------------------------
# Withdrawals: charges, manual / automatic payouts, logs, history
# ---------------------------------------------------------------------------
class PayoutTests(Base):
    def setUp(self):
        super().setUp()
        self.wallet = UserWallet.objects.create(user=self.cust, balance=D("5000"))
        self.pm = PayoutMethod.objects.get(code="jazzcash")
        self.pm.fee_fixed, self.pm.fee_percent = D("20"), D("1")
        self.pm.save()

    def request(self, amount="1000", account="03001234567"):
        from UserPanel.services import create_withdrawal
        return create_withdrawal(self.cust, {"amount": D(amount), "method": "jazzcash", "account_title": "Ali",
                                             "account_number": account})

    def test_fee_rules(self):
        self.assertEqual(self.pm.fee_for(D("1000")), D("30.00"))
        self.pm.fee_min, self.pm.fee_max = D("50"), D("100")
        self.assertEqual(self.pm.fee_for(D("1000")), D("50.00"))
        self.assertEqual(self.pm.fee_for(D("20000")), D("100.00"))
        self.assertEqual(self.pm.fee_text(), "1% + Rs 20 (min Rs 50) (max Rs 100)")

    def test_request_holds_full_amount_and_records_fee(self):
        w = self.request()
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance, D("4000"))
        self.assertEqual((w.fee, w.net_amount), (D("30.00"), D("970.00")))
        self.assertTrue(PayoutEvent.objects.filter(withdrawal=w, kind="requested").exists())

    def test_withdraw_page_shows_charge(self):
        r = self.cust_client().get(reverse("home:user-withdraw"))
        self.assertContains(r, "Withdrawal charges")
        self.assertContains(r, "1% + Rs 20")
        self.assertContains(r, 'id="feeNet"')

    def test_manual_payout_needs_reference(self):
        from UserPanel.services import approve_withdrawal
        w = self.request()
        ok, msg = approve_withdrawal(w.pk, self.root)
        self.assertFalse(ok)
        w.refresh_from_db()
        self.assertEqual(w.status, "failed")
        ok, msg = approve_withdrawal(w.pk, self.root, reference="JC-998877")
        self.assertTrue(ok, msg)
        w.refresh_from_db()
        self.assertEqual((w.status, w.gateway_reference), ("paid", "JC-998877"))
        self.assertTrue(PayoutEvent.objects.filter(withdrawal=w, kind="payout_paid", reference="JC-998877").exists())

    def test_automatic_test_provider(self):
        from UserPanel.services import approve_withdrawal
        self.pm.mode, self.pm.provider, self.pm.environment = "api", "test", "sandbox"
        self.pm.save()
        w = self.request()
        ok, _ = approve_withdrawal(w.pk, self.root)
        w.refresh_from_db()
        self.assertTrue(ok)
        self.assertTrue(w.gateway_reference.startswith("TESTPAYOUT-"))
        bad = self.request(account="03000000000")
        ok, msg = approve_withdrawal(bad.pk, self.root)
        self.assertFalse(ok)
        self.assertIn("Simulated failure", msg)

    def test_http_provider_sends_signed_json(self):
        from UserPanel.services import approve_withdrawal
        self.pm.mode, self.pm.provider, self.pm.api_url = "api", "http", "https://payouts.example/send"
        self.pm.api_key, self.pm.api_secret = "k", "s3cret"
        self.pm.save()
        w = self.request()
        reply = mock.Mock(status_code=200, content=b"x")
        reply.json.return_value = {"status": "processing", "reference": "PX1"}
        with mock.patch("UserPanel.payouts.requests.post", return_value=reply) as post:
            ok, msg = approve_withdrawal(w.pk, self.root)
        self.assertTrue(ok)
        kw = post.call_args.kwargs
        body = json.loads(kw["data"])
        self.assertEqual((body["amount"], body["reference"]), ("970.00", f"WD-{w.pk}"))
        expected = hmac.new(b"s3cret", kw["headers"]["X-Timestamp"].encode() + b"." + kw["data"],
                            hashlib.sha256).hexdigest()
        self.assertEqual(kw["headers"]["X-Signature"], expected)
        w.refresh_from_db()
        self.assertEqual(w.status, "processing")
        ok, _ = approve_withdrawal(w.pk, self.root)                      # staff confirm arrival
        w.refresh_from_db()
        self.assertEqual(w.status, "paid")

    def test_admin_pages_and_history(self):
        w = self.request()
        admin = Client()
        admin.force_login(self.root)
        self.assertContains(admin.get(reverse("admin-withdrawals")), "send Rs. 970.00")
        self.assertContains(admin.get(reverse("admin_payout_settings")), "1% + Rs 20")
        self.assertContains(admin.get(reverse("admin_payout_logs")), "requested")
        self.assertContains(admin.get(reverse("admin_transactions")), f"Withdrawal #{w.pk}")
        r = self.cust_client().get(reverse("home:user-transactions"))
        self.assertContains(r, f"Withdrawal #{w.pk}")
        self.assertNotContains(self.cust_client(self.other).get(reverse("home:user-transactions")),
                               f"Withdrawal #{w.pk}")


# ---------------------------------------------------------------------------
# Google Merchant API
# ---------------------------------------------------------------------------
class MerchantApiTests(Base):
    def setUp(self):
        super().setUp()
        from storefront.models import SeoSettings
        s = SeoSettings.get()
        s.merchant_api_enabled, s.merchant_auto_sync = True, False
        s.merchant_account_id, s.merchant_data_source_id = "123456", "777"
        s.google_service_account = "{}"
        s.save()
        self.product.slug = "lawn-suit"
        self.product.save()

    def test_product_input_format(self):
        from storefront.merchant import product_input
        body = product_input(self.product)
        a = body["productAttributes"]
        self.assertEqual((body["offerId"], body["contentLanguage"], body["feedLabel"]), ("LS", "en", "PK"))
        self.assertEqual(a["price"], {"amountMicros": "2500000000", "currencyCode": "PKR"})
        self.assertEqual(a["availability"], "IN_STOCK")
        self.assertEqual(a["condition"], "NEW")

    def test_upsert_calls_merchant_api(self):
        from storefront import merchant
        from storefront.models import MerchantProduct
        ok_reply = mock.Mock(status_code=200)
        with mock.patch.object(merchant, "parse_service_account", return_value={}), \
                mock.patch.object(merchant, "_google_token", return_value="tok"), \
                mock.patch.object(merchant, "product_input", return_value={
                    "offerId": "LS", "productAttributes": {"imageLink": "https://shop.test/a.png"}}), \
                mock.patch.object(merchant.requests, "post", return_value=ok_reply) as post:
            ok, _ = merchant.upsert(self.product)
        self.assertTrue(ok)
        url = post.call_args.args[0]
        self.assertEqual(url, "https://merchantapi.googleapis.com/products/v1/accounts/123456/productInputs:insert")
        self.assertEqual(post.call_args.kwargs["params"], {"dataSource": "accounts/123456/dataSources/777"})
        self.assertEqual(MerchantProduct.objects.get(product=self.product).status, "synced")

    def test_admin_preview(self):
        admin = Client()
        admin.force_login(self.root)
        r = admin.get(reverse("storefront_merchant_preview", args=[self.product.pk]))
        self.assertEqual(r.json()["product"]["offerId"], "LS")


class MobileLogoutTests(Base):
    def test_account_pages_offer_logout(self):
        r = self.cust_client().get(reverse("home:user-transactions"))
        self.assertContains(r, 'id="mobileNav"')
        self.assertGreaterEqual(r.content.decode().count(f'href="{reverse("logout")}"'), 3)  # dropdown, sidebar, menu
