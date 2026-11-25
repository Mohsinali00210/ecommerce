"""
JazzCash hosted checkout ("Page Redirection", API version 1.1).

Flow
  1. The browser POSTs pp_* fields to {base}/CustomerPortal/transactionmanagement/merchantform/
  2. The customer pays (JazzCash wallet / card / voucher) on JazzCash's page.
  3. JazzCash POSTs the result (pp_* fields + pp_SecureHash) to pp_ReturnURL.
     pp_ResponseCode "000" = paid, "124" = voucher created, waiting for cash payment.
  4. IPN (optional, set the URL in the JazzCash portal): same fields, JSON or form encoded.

Secure hash: every non-empty field whose name starts with "pp" (except pp_SecureHash), sorted by
name, values joined with "&", prefixed with "<integrity salt>&", HMAC-SHA256 keyed with the
integrity salt, upper-case hex.

Admin fields: API key = Merchant ID, Secret key = Integrity salt, Webhook secret = Password.
Base URLs: sandbox https://sandbox.jazzcash.com.pk, live https://payments.jazzcash.com.pk
"""
import hashlib
import hmac
import json
import re
from datetime import timedelta
from decimal import Decimal

from django.utils import timezone

from . import register
from .base import BaseGateway, GatewayError, ReturnResult, Session, WebhookResult

FORM_PATH = "/CustomerPortal/transactionmanagement/merchantform/"
PAID, PENDING = "000", "124"


def secure_hash(fields, salt):
    values = [str(fields[k]) for k in sorted(fields)
              if k.lower().startswith("pp") and k != "pp_SecureHash" and str(fields[k]) != ""]
    message = "&".join([salt] + values)
    return hmac.new(salt.encode(), message.encode(), hashlib.sha256).hexdigest().upper()


@register("jazzcash")
class JazzCashGateway(BaseGateway):
    display_name = "JazzCash"
    checkout_label = "JazzCash"
    checkout_description = "Pay with your JazzCash wallet or card"
    checkout_icon = "bi-phone"
    required_fields = ("api_key", "secret_key", "webhook_secret")
    credential_labels = {"api_key": "Merchant ID", "secret_key": "Integrity salt", "webhook_secret": "Password"}
    extra_fields = {
        "txn_type": ("Transaction type", "Empty = customer chooses. MWALLET, MPAY (card) or OTC (voucher)", ""),
        "bank_id": ("Bank ID", "Only if JazzCash gave you one (sandbox: TBANK)", ""),
        "product_id": ("Product ID", "Only if JazzCash gave you one (sandbox: RETL)", ""),
    }
    default_urls = ("https://sandbox.jazzcash.com.pk", "https://payments.jazzcash.com.pk")

    def _salt(self):
        return self.gateway.secret_key or ""

    def build_fields(self, payment, return_url):
        now = timezone.localtime()
        ref = f"T{now:%Y%m%d%H%M%S}{payment.pk % 100000:05d}"[:20]
        order_no = re.sub(r"[^A-Za-z0-9]", "", str(payment.order.order_number or payment.order_id))[:20]
        fields = {
            "pp_Version": "1.1",
            "pp_TxnType": self.extra("txn_type"),
            "pp_Language": "EN",
            "pp_MerchantID": self.gateway.api_key,
            "pp_SubMerchantID": "",
            "pp_Password": self.gateway.webhook_secret,
            "pp_BankID": self.extra("bank_id"),
            "pp_ProductID": self.extra("product_id"),
            "pp_TxnRefNo": ref,
            "pp_Amount": str(int((Decimal(payment.amount) * 100).to_integral_value())),
            "pp_TxnCurrency": "PKR",
            "pp_TxnDateTime": f"{now:%Y%m%d%H%M%S}",
            "pp_BillReference": order_no or "order",
            "pp_Description": f"Order {payment.order.order_number}"[:100],
            "pp_TxnExpiryDateTime": f"{now + timedelta(hours=24):%Y%m%d%H%M%S}",
            "pp_ReturnURL": return_url,
            "ppmpf_1": str(payment.pk), "ppmpf_2": "", "ppmpf_3": "", "ppmpf_4": "", "ppmpf_5": "",
        }
        fields["pp_SecureHash"] = secure_hash(fields, self._salt())
        return fields

    def start(self, payment, return_url, cancel_url):
        if not self.is_configured(self.gateway):
            raise GatewayError("JazzCash is not configured.")
        fields = self.build_fields(payment, return_url)
        return Session(tracker=fields["pp_TxnRefNo"], redirect_url=self.gateway.base_url + FORM_PATH,
                       post_fields=fields, raw={"pp_TxnRefNo": fields["pp_TxnRefNo"]})

    def verify_return(self, data):
        sig = data.get("pp_SecureHash", "")
        return bool(sig) and hmac.compare_digest(secure_hash(data, self._salt()), sig.upper())

    def _result(self, data):
        code = str(data.get("pp_ResponseCode", ""))
        ref = data.get("pp_RetreivalReferenceNo") or data.get("pp_TxnRefNo") or ""
        if code == PAID:
            return "paid", ref
        if code == PENDING:
            return "pending", ref
        return "failed", ref

    def handle_return(self, payment, data):
        if data.get("pp_TxnRefNo") != payment.tracker or not self.verify_return(data):
            return ReturnResult("pending", reason="JazzCash response could not be verified")
        event, ref = self._result(data)
        return ReturnResult(event, reference=ref, verified=True,
                            reason=data.get("pp_ResponseMessage", "") if event == "failed" else "")

    def parse_webhook(self, body, headers):
        try:
            data = json.loads(body or b"{}")
        except ValueError:
            from urllib.parse import parse_qsl
            data = dict(parse_qsl(body.decode("utf-8", "replace")))
        if not self.verify_return(data):
            raise GatewayError("Invalid JazzCash secure hash")
        event, ref = self._result(data)
        return WebhookResult(event=event if event != "pending" else "ignored",
                             tracker=data.get("pp_TxnRefNo", ""), reference=ref, raw=data)

    def webhook_ack(self):
        body = {"pp_ResponseCode": "000", "pp_ResponseMessage": "IPN received"}
        body["pp_SecureHash"] = secure_hash(body, self._salt())
        return json.dumps(body), "application/json"
