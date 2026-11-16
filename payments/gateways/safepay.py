"""
Safepay (getsafepay.com) hosted checkout.

Flow
  1. POST {base}/order/v1/init {client, amount, currency, environment} -> data.token (the "tracker")
  2. Redirect the customer to {base}/components?env=..&beacon=<tracker>&order_id=..&source=..
     &redirect_url=..&cancel_url=..
  3. On success Safepay POSTs tracker, token, ref, sig, order_id to redirect_url.
     sig == HMAC-SHA256(tracker, secret_key)  -> payment is genuine.
  4. Webhooks: header X-SFPY-SIGNATURE == HMAC-SHA512(body, webhook_secret);
     events payment.succeeded / payment.failed.

Base URLs: sandbox https://sandbox.api.getsafepay.com, live https://api.getsafepay.com
(checkout pages: sandbox .../components, live https://www.getsafepay.com/components).
"""
import hashlib
import hmac
import json
from urllib.parse import urlencode

import requests

from . import register
from .base import BaseGateway, GatewayError, Session, WebhookResult

LIVE_CHECKOUT = "https://www.getsafepay.com/components"


def _first(d, *keys):
    for k in keys:
        cur = d
        for part in k.split("."):
            cur = cur.get(part) if isinstance(cur, dict) else None
        if cur not in (None, ""):
            return cur
    return None


@register("safepay")
class SafepayGateway(BaseGateway):
    display_name = "Safepay"

    @property
    def env(self):
        return "production" if self.gateway.environment == "live" else "sandbox"

    def checkout_base(self):
        return LIVE_CHECKOUT if self.env == "production" else self.gateway.base_url + "/components"

    def start(self, payment, return_url, cancel_url):
        body = {"client": self.gateway.api_key, "amount": float(payment.amount),
                "currency": payment.currency, "environment": self.env}
        try:
            r = requests.post(self.gateway.base_url + "/order/v1/init", json=body, timeout=self.timeout)
        except requests.RequestException as exc:
            raise GatewayError(f"Could not reach Safepay: {exc}")
        try:
            data = r.json()
        except ValueError:
            raise GatewayError(f"Safepay returned HTTP {r.status_code}", {"body": r.text[:1000]})
        token = _first(data, "data.token", "data.tracker.token", "token")
        if r.status_code >= 400 or not token:
            msg = _first(data, "status.errors", "message", "error") or f"HTTP {r.status_code}"
            raise GatewayError(f"Safepay rejected the payment: {msg}", data)
        params = {"env": self.env, "beacon": token, "source": "shanzee", "order_id": payment.order.order_number,
                  "redirect_url": return_url, "cancel_url": cancel_url}
        return Session(tracker=str(token), redirect_url=f"{self.checkout_base()}?{urlencode(params)}", raw=data)

    def verify_return(self, data):
        tracker, sig = data.get("tracker") or data.get("beacon"), data.get("sig")
        if not tracker or not sig or not self.gateway.secret_key:
            return False
        expected = hmac.new(self.gateway.secret_key.encode(), str(tracker).encode(), hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, str(sig))

    def _webhook_signature_ok(self, body, signature):
        secret = (self.gateway.webhook_secret or "").encode()
        if not secret or not signature:
            return False
        candidates = [body]
        try:  # Safepay's SDK signs a re-encoded JSON body; accept the common encodings
            obj = json.loads(body)
            candidates.append(json.dumps(obj, separators=(",", ":"), ensure_ascii=False).encode())
            candidates.append(json.dumps(obj, separators=(",", ":")).encode())
        except ValueError:
            pass
        for c in candidates:
            if hmac.compare_digest(hmac.new(secret, c, hashlib.sha512).hexdigest(), signature.strip()):
                return True
        return False

    def parse_webhook(self, body, headers):
        sig = headers.get("X-SFPY-SIGNATURE") or headers.get("x-sfpy-signature") or ""
        if not self._webhook_signature_ok(body, sig):
            raise GatewayError("Invalid webhook signature")
        data = json.loads(body or b"{}")
        etype = str(_first(data, "type", "event") or "")
        tracker = str(_first(data, "data.tracker.token", "data.tracker", "data.token", "data.beacon") or "")
        ref = str(_first(data, "data.reference", "data.ref", "data.transaction.reference", "data.id") or "")
        event = {"payment.succeeded": "paid", "payment.failed": "failed"}.get(etype, "ignored")
        return WebhookResult(event=event, tracker=tracker, reference=ref, raw=data)
