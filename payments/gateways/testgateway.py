"""
Test gateway: a built-in payment page that simulates success / failure / cancel, so the
whole checkout -> payment -> order flow can be tested without any provider account.

It is only offered at checkout to staff users (or to everyone while DEBUG is on), and its
results are signed with Django's SECRET_KEY so they can't be forged from the browser.
Never leave it as the only online method in production.
"""
from django.core import signing
from django.utils.crypto import get_random_string
from django.urls import reverse

from . import register
from .base import BaseGateway, ReturnResult, Session, WebhookResult

SALT = "payments.testgateway"


def sign(data):
    return signing.dumps(data, salt=SALT)


def unsign(token, max_age=3600):
    try:
        return signing.loads(token, salt=SALT, max_age=max_age)
    except signing.BadSignature:
        return None


@register("test")
class TestGateway(BaseGateway):
    display_name = "Test gateway (sandbox)"
    checkout_label = "Test payment (sandbox)"
    checkout_description = "Simulated payment - no real money (staff only)"
    checkout_icon = "bi-bug"
    required_fields = ()
    needs_base_url = False
    has_webhook = False
    sandbox_only = True
    credential_labels = {"api_key": "Not used", "secret_key": "Not used", "webhook_secret": "Not used"}

    def start(self, payment, return_url, cancel_url):
        tracker = f"TEST-{payment.pk}-{get_random_string(8)}"
        token = sign({"p": payment.pk, "t": tracker, "r": return_url, "c": cancel_url})
        return Session(tracker=tracker, redirect_url=reverse("payments:test_gateway", args=[token]))

    def verify_return(self, data):
        return unsign(data.get("result", "")) is not None

    def handle_return(self, payment, data):
        res = unsign(data.get("result", ""))
        if not res or res.get("t") != payment.tracker or res.get("p") != payment.pk:
            return ReturnResult("pending", reason="test result not verified")
        if res.get("outcome") == "paid":
            return ReturnResult("paid", reference=f"TESTREF-{payment.pk}", verified=True)
        return ReturnResult("failed", reason="Simulated failure", verified=True)

    def parse_webhook(self, body, headers):
        return WebhookResult(event="ignored")

    def test_connection(self):
        return "The test gateway needs no credentials. It is shown at checkout to staff only (or to everyone in DEBUG)."
