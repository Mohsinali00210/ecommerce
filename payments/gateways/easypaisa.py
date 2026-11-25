"""
Easypaisa "Easypay" hosted checkout.

Flow
  1. The browser POSTs storeId, amount, postBackURL, orderRefNum, expiryDate, autoRedirect,
     merchantHashedReq ... to {base}/easypay/Index.jsf
  2. Easypaisa sends the browser back to postBackURL with ?auth_token=...
  3. The browser POSTs auth_token + postBackURL to {base}/easypay/Confirm.jsf, the customer pays.
  4. Easypaisa sends the browser back to postBackURL with ?status=0000&desc=..&orderRefNumber=..

The final redirect is NOT signed, so it is never trusted on its own: the payment is confirmed
with the Inquire Transaction API (server to server). Without inquiry credentials the payment
stays pending for staff to confirm in Admin > Payments.

merchantHashedReq: the request fields "key=value" joined with "&" in alphabetical order,
AES-128/ECB/PKCS5 encrypted with the hash key, base64.

Admin fields: API key = Store ID, Secret key = Hash key,
Webhook secret = inquiry API "username:password". Extra: account number (for inquiry).
Base URLs: sandbox https://easypaystg.easypaisa.com.pk, live https://easypay.easypaisa.com.pk
"""
import base64
import re
from datetime import timedelta
from decimal import Decimal

import requests
from django.utils import timezone

from . import register
from .base import BaseGateway, GatewayError, ReturnResult, Session

INDEX_PATH = "/easypay/Index.jsf"
CONFIRM_PATH = "/easypay/Confirm.jsf"
INQUIRE_PATH = "/easypay-service/rest/v4/inquire-transaction"


def hashed_request(fields, hash_key):
    from cryptography.hazmat.primitives import padding
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    plain = "&".join(f"{k}={fields[k]}" for k in sorted(fields) if fields[k] not in ("", None))
    key = hash_key.encode()
    if len(key) not in (16, 24, 32):
        raise GatewayError("The Easypaisa hash key must be 16 characters.")
    padder = padding.PKCS7(128).padder()
    data = padder.update(plain.encode()) + padder.finalize()
    enc = Cipher(algorithms.AES(key), modes.ECB()).encryptor()  # noqa: S305 - required by Easypaisa
    return base64.b64encode(enc.update(data) + enc.finalize()).decode()


@register("easypaisa")
class EasypaisaGateway(BaseGateway):
    display_name = "Easypaisa"
    checkout_label = "Easypaisa"
    checkout_description = "Pay with your Easypaisa account or card"
    checkout_icon = "bi-phone-fill"
    credential_labels = {"api_key": "Store ID", "secret_key": "Hash key",
                         "webhook_secret": "Inquiry API username:password"}
    extra_fields = {
        "payment_method": ("Payment method", "Empty = customer chooses. MA_PAYMENT_METHOD, CC_PAYMENT_METHOD "
                                             "or OTC_PAYMENT_METHOD", ""),
        "account_num": ("Merchant account number", "Needed by the Inquire Transaction API", ""),
    }
    default_urls = ("https://easypaystg.easypaisa.com.pk", "https://easypay.easypaisa.com.pk")
    has_webhook = False

    def order_ref(self, payment):
        return re.sub(r"[^A-Za-z0-9]", "", f"{payment.order.order_number}{payment.pk}")[:30]

    def start(self, payment, return_url, cancel_url):
        if not self.is_configured(self.gateway):
            raise GatewayError("Easypaisa is not configured.")
        now = timezone.localtime()
        email = getattr(payment.order.user, "email", "") or ""
        fields = {
            "amount": f"{Decimal(payment.amount):.1f}",
            "autoRedirect": "1",
            "emailAddr": email,
            "expiryDate": f"{now + timedelta(hours=24):%Y%m%d %H%M%S}",
            "orderRefNum": self.order_ref(payment),
            "paymentMethod": self.extra("payment_method"),
            "postBackURL": return_url,
            "storeId": self.gateway.api_key,
        }
        fields["merchantHashedReq"] = hashed_request(fields, self.gateway.secret_key)
        return Session(tracker=fields["orderRefNum"], redirect_url=self.gateway.base_url + INDEX_PATH,
                       post_fields={k: v for k, v in fields.items() if v != ""})

    def verify_return(self, data):
        return False  # the browser return is unsigned; see inquire()

    def inquire(self, payment):
        """Inquire Transaction API -> ReturnResult."""
        creds = self.gateway.webhook_secret or ""
        if ":" not in creds:
            return ReturnResult("pending", reason="Inquiry API credentials not set - confirm the payment manually")
        body = {"orderId": payment.tracker, "storeId": self.gateway.api_key,
                "accountNum": self.extra("account_num")}
        headers = {"Credentials": base64.b64encode(creds.encode()).decode(), "Content-Type": "application/json"}
        try:
            r = requests.post(self.gateway.base_url + INQUIRE_PATH, json=body, headers=headers,
                              timeout=self.timeout)
            data = r.json()
        except (requests.RequestException, ValueError) as exc:
            return ReturnResult("pending", reason=f"Easypaisa inquiry failed: {exc.__class__.__name__}")
        status = str(data.get("transactionStatus", "")).upper()
        ref = str(data.get("transactionId") or data.get("orderId") or "")
        if data.get("responseCode") == "0000" and status == "PAID":
            return ReturnResult("paid", reference=ref, verified=True, raw=data)
        if status in ("FAILED", "REVERSED", "EXPIRED", "DROPPED"):
            return ReturnResult("failed", reference=ref, verified=True, reason=status.lower(), raw=data)
        return ReturnResult("pending", reason=status or data.get("responseDesc", ""), raw=data)

    check_status = inquire

    def handle_return(self, payment, data):
        if data.get("auth_token"):
            # step 2: confirm on Easypaisa's page
            return ReturnResult("redirect", session=Session(
                tracker=payment.tracker, redirect_url=self.gateway.base_url + CONFIRM_PATH,
                post_fields={"auth_token": data["auth_token"], "postBackURL": data.get("postBackURL", "")}))
        if data.get("orderRefNumber") and data.get("orderRefNumber") != payment.tracker:
            return ReturnResult("pending", reason="order reference mismatch")
        if data.get("status") and data.get("status") != "0000":
            # unsigned "failed" is harmless to trust: it only lets the customer retry
            return ReturnResult("failed", reason=data.get("desc", "Payment not completed"))
        return self.inquire(payment)

    def test_connection(self):
        super().test_connection()
        if len((self.gateway.secret_key or "").encode()) not in (16, 24, 32):
            raise GatewayError("The hash key must be 16 characters long.")
        return "Settings look complete. Place a test order to confirm the full flow."
