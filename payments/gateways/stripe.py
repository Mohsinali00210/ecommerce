"""
Stripe Checkout (hosted page), plain REST calls - no SDK needed.

Flow
  1. POST https://api.stripe.com/v1/checkout/sessions -> {id, url}; the customer pays on `url`.
  2. Stripe redirects to success_url?session_id=<id>; we fetch the session server side and only
     mark the payment paid when payment_status == "paid".
  3. Webhooks (Dashboard > Developers > Webhooks, events checkout.session.*):
     header Stripe-Signature "t=<ts>,v1=<sig>", sig = HMAC-SHA256(webhook secret, "<ts>.<body>").

Admin fields: API key = publishable key (optional), Secret key = secret key (sk_test_ / sk_live_),
Webhook secret = endpoint signing secret (whsec_...). Base URL https://api.stripe.com
"""
import hashlib
import hmac
import json
import time
from decimal import Decimal

import requests

from . import register
from .base import BaseGateway, GatewayError, ReturnResult, Session, WebhookResult

TOLERANCE = 300  # seconds


@register("stripe")
class StripeGateway(BaseGateway):
    display_name = "Stripe"
    checkout_label = "Credit / debit card"
    checkout_description = "Visa, Mastercard and more via Stripe"
    checkout_icon = "bi-credit-card"
    required_fields = ("secret_key",)
    credential_labels = {"api_key": "Publishable key (optional)", "secret_key": "Secret key",
                         "webhook_secret": "Webhook signing secret (whsec_...)"}
    extra_fields = {"currency": ("Currency", "ISO code Stripe charges in", "pkr")}
    default_urls = ("https://api.stripe.com", "https://api.stripe.com")

    def _call(self, method, path, data=None):
        try:
            r = requests.request(method, self.gateway.base_url + path, data=data, timeout=self.timeout,
                                 auth=(self.gateway.secret_key, ""))
            body = r.json()
        except requests.RequestException as exc:
            raise GatewayError(f"Could not reach Stripe: {exc.__class__.__name__}")
        except ValueError:
            raise GatewayError(f"Stripe returned HTTP {r.status_code}")
        if r.status_code >= 400:
            raise GatewayError(f"Stripe: {body.get('error', {}).get('message', r.status_code)}", body)
        return body

    def start(self, payment, return_url, cancel_url):
        sep = "&" if "?" in return_url else "?"
        data = {
            "mode": "payment",
            "success_url": f"{return_url}{sep}session_id={{CHECKOUT_SESSION_ID}}",
            "cancel_url": cancel_url,
            "client_reference_id": str(payment.pk),
            "metadata[payment_id]": str(payment.pk),
            "metadata[order_number]": str(payment.order.order_number),
            "line_items[0][quantity]": "1",
            "line_items[0][price_data][currency]": self.extra("currency").lower(),
            "line_items[0][price_data][unit_amount]": str(int((Decimal(payment.amount) * 100).to_integral_value())),
            "line_items[0][price_data][product_data][name]": f"Order {payment.order.order_number}",
        }
        email = getattr(payment.order.user, "email", "")
        if email:
            data["customer_email"] = email
        s = self._call("POST", "/v1/checkout/sessions", data)
        return Session(tracker=s["id"], redirect_url=s["url"], raw={"id": s["id"]})

    def verify_return(self, data):
        return False  # always checked server side, see handle_return

    def check_status(self, payment):
        s = self._call("GET", f"/v1/checkout/sessions/{payment.tracker}")
        ref = s.get("payment_intent") or s.get("id") or ""
        if s.get("payment_status") == "paid":
            return ReturnResult("paid", reference=str(ref), verified=True, raw={"id": s.get("id")})
        if s.get("status") == "expired":
            return ReturnResult("failed", reason="Checkout session expired", verified=True)
        return ReturnResult("pending", reason=s.get("payment_status", ""))

    def handle_return(self, payment, data):
        if not data.get("session_id") or data.get("session_id") != payment.tracker:
            return ReturnResult("pending", reason="session id mismatch")
        try:
            return self.check_status(payment)
        except GatewayError as exc:
            return ReturnResult("pending", reason=str(exc))

    def _signature_ok(self, body, header):
        secret = self.gateway.webhook_secret or ""
        if not secret or not header:
            return False
        parts = {}
        for item in header.split(","):
            k, _, v = item.strip().partition("=")
            parts.setdefault(k, []).append(v)
        ts = (parts.get("t") or [""])[0]
        if not ts.isdigit() or abs(time.time() - int(ts)) > TOLERANCE:
            return False
        expected = hmac.new(secret.encode(), ts.encode() + b"." + body, hashlib.sha256).hexdigest()
        return any(hmac.compare_digest(expected, s) for s in parts.get("v1", []))

    def parse_webhook(self, body, headers):
        if not self._signature_ok(body, headers.get("Stripe-Signature", "")):
            raise GatewayError("Invalid Stripe signature")
        evt = json.loads(body or b"{}")
        obj = evt.get("data", {}).get("object", {})
        etype = evt.get("type", "")
        event = "ignored"
        if etype in ("checkout.session.completed", "checkout.session.async_payment_succeeded"):
            event = "paid" if obj.get("payment_status") == "paid" else "ignored"
        elif etype in ("checkout.session.async_payment_failed", "checkout.session.expired"):
            event = "failed"
        return WebhookResult(event=event, tracker=obj.get("id", ""), reference=str(obj.get("payment_intent") or ""),
                             raw={"id": evt.get("id"), "type": etype})

    def test_connection(self):
        super().test_connection()
        b = self._call("GET", "/v1/balance")
        return f"Stripe accepted the secret key ({'live' if b.get('livemode') else 'test'} mode)."
