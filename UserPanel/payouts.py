"""Sending approved wallet withdrawals to the customer's account.

Each withdrawal method (JazzCash, Easypaisa, bank, Stripe) has a PayoutMethod row
(Admin > Withdrawals > Payout settings) that decides how the money goes out:

  manual   staff send the money themselves (bank app, JazzCash/Easypaisa business portal),
           then approve with the transaction reference. Nothing is sent automatically.
  api      sent automatically on approval, through `provider`:
             test    sandbox simulator (account number ending in 0000 fails), no real money
             stripe  Stripe Connect transfer to the account id the user entered (acct_...)
             http    your payout service / bank middleware: signed JSON POST to api_url

Generic payout API ("http") contract
  POST <api_url>   Content-Type: application/json
  Headers  X-Api-Key: <api key>   X-Timestamp: <unix seconds>
           X-Signature: hex HMAC-SHA256(<api secret>, "<timestamp>.<raw body>")
  Body     {"reference": "WD-12", "amount": "990.00", "currency": "PKR", "method": "jazzcash",
            "account_title": "...", "account_number": "...", "bank_name": "...", "environment": "sandbox"}
  Reply    2xx {"status": "paid" | "processing" | "failed", "reference": "<provider txn id>", "message": ""}

send_payout() returns {"reference", "status": "paid" | "processing", "provider", "data"} or raises PayoutError.
"""
import hashlib
import hmac
import json
import time
from decimal import Decimal

import requests

TIMEOUT = 30


class PayoutError(Exception):
    def __init__(self, message, data=None):
        super().__init__(message)
        self.data = data or {}


def method_for(code):
    from payments.models import PayoutMethod
    return PayoutMethod.objects.filter(code=code).first()


def _payload(w, pm):
    return {
        "reference": f"WD-{w.pk}",
        "amount": f"{Decimal(w.payout_amount):.2f}",
        "currency": "PKR",
        "method": w.method,
        "account_title": w.account_title,
        "account_number": w.account_number,
        "bank_name": w.bank_name or "",
        "environment": pm.environment,
    }


def _test(w, pm):
    if pm.environment != "sandbox":
        raise PayoutError("The test payout provider only works in sandbox mode.")
    if (w.account_number or "").strip().endswith("0000"):
        raise PayoutError("Simulated failure: account rejected by the test provider (number ends in 0000).")
    return {"reference": f"TESTPAYOUT-{w.pk}-{int(time.time())}", "status": "paid", "data": {"simulated": True}}


def _stripe(w, pm):
    dest = (w.account_number or "").strip()
    if not dest.startswith("acct_"):
        raise PayoutError("For Stripe the account number must be the user's Stripe account id (acct_...).")
    if not pm.api_key:
        raise PayoutError("Add the Stripe secret key in Payout settings.")
    data = {"amount": str(int((Decimal(w.payout_amount) * 100).to_integral_value())), "currency": "pkr",
            "destination": dest, "transfer_group": f"WD-{w.pk}", "metadata[withdrawal_id]": str(w.pk)}
    try:
        r = requests.post("https://api.stripe.com/v1/transfers", data=data, auth=(pm.api_key, ""), timeout=TIMEOUT,
                          headers={"Idempotency-Key": f"shanzee-withdrawal-{w.pk}"})
        body = r.json()
    except (requests.RequestException, ValueError) as exc:
        raise PayoutError(f"Could not reach Stripe: {exc.__class__.__name__}")
    if r.status_code >= 400:
        raise PayoutError(f"Stripe: {body.get('error', {}).get('message', r.status_code)}", body)
    return {"reference": body.get("id", ""), "status": "paid", "data": {"id": body.get("id")}}


def _http(w, pm):
    if not pm.api_url:
        raise PayoutError("Add the payout API URL in Payout settings.")
    body = json.dumps(_payload(w, pm), separators=(",", ":")).encode()
    ts = str(int(time.time()))
    sig = hmac.new((pm.api_secret or "").encode(), ts.encode() + b"." + body, hashlib.sha256).hexdigest()
    headers = {"Content-Type": "application/json", "X-Api-Key": pm.api_key or "", "X-Timestamp": ts,
               "X-Signature": sig, "Idempotency-Key": f"shanzee-withdrawal-{w.pk}"}
    try:
        r = requests.post(pm.api_url, data=body, headers=headers, timeout=TIMEOUT)
        reply = r.json() if r.content else {}
    except requests.RequestException as exc:
        raise PayoutError(f"Could not reach the payout API: {exc.__class__.__name__}")
    except ValueError:
        raise PayoutError(f"The payout API returned HTTP {r.status_code} without JSON.")
    status = str(reply.get("status", "")).lower()
    if r.status_code >= 400 or status == "failed":
        raise PayoutError(reply.get("message") or f"Payout API refused it (HTTP {r.status_code}).", reply)
    if status not in ("paid", "processing"):
        raise PayoutError(f"Unexpected payout API reply: {reply}"[:300], reply)
    return {"reference": str(reply.get("reference", ""))[:120], "status": status, "data": reply}


PROVIDERS = {"test": _test, "stripe": _stripe, "http": _http}


def send_payout(withdrawal, reference=""):
    """Called when staff approve. Manual methods need the reference of the transfer staff made."""
    pm = method_for(withdrawal.method)
    if pm is None or not pm.automatic:
        reference = (reference or "").strip()
        if not reference:
            raise PayoutError("This method is paid manually: send the money first, then enter the "
                              "transaction reference / ID to approve.")
        return {"reference": reference[:120], "status": "paid", "provider": "manual", "data": {}}
    fn = PROVIDERS.get(pm.provider)
    if not fn:
        raise PayoutError(f"Unknown payout provider '{pm.provider}'.")
    result = fn(withdrawal, pm)
    result["provider"] = pm.provider
    return result
