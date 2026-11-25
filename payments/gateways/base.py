from dataclasses import dataclass, field


class GatewayError(Exception):
    def __init__(self, message, data=None):
        super().__init__(message)
        self.data = data or {}


@dataclass
class Session:
    """Where to send the customer. `post_fields` set -> the browser auto-submits a form
    (POST) to `redirect_url` with these fields (JazzCash / Easypaisa hosted pages)."""
    tracker: str
    redirect_url: str
    raw: dict = field(default_factory=dict)
    post_fields: dict = None


@dataclass
class WebhookResult:
    event: str              # "paid", "failed" or "ignored"
    tracker: str = ""
    reference: str = ""
    raw: dict = field(default_factory=dict)


@dataclass
class ReturnResult:
    """Outcome of the customer's browser coming back from the gateway.
    event: "paid" (verified), "failed", "cancelled", "pending" (not verifiable here: wait
    for the webhook / admin) or "redirect" (another step on the gateway: see `session`)."""
    event: str
    reference: str = ""
    reason: str = ""
    verified: bool = False
    session: Session = None
    raw: dict = field(default_factory=dict)


class BaseGateway:
    code = ""
    display_name = ""
    checkout_label = "Pay online"
    checkout_description = "Pay securely online"
    checkout_icon = "bi-credit-card-2-front"
    timeout = 25
    # Which PaymentGateway fields this gateway needs, and what to call them in the admin.
    required_fields = ("api_key", "secret_key")
    needs_base_url = True
    credential_labels = {"api_key": "API key", "secret_key": "Secret key", "webhook_secret": "Webhook secret"}
    extra_fields = {}           # {"key": ("Label", "help text", "default")}
    default_urls = ("", "")     # (sandbox, live)
    has_webhook = True
    sandbox_only = False

    def __init__(self, gateway):
        self.gateway = gateway

    # --- configuration -------------------------------------------------------
    @classmethod
    def is_configured(cls, gateway):
        if cls.needs_base_url and not gateway.base_url:
            return False
        return all(getattr(gateway, f, "") for f in cls.required_fields)

    def extra(self, key):
        default = self.extra_fields.get(key, ("", "", ""))[2]
        return (self.gateway.extra or {}).get(key) or default

    def test_connection(self):
        """Quick check from the admin. Returns a message or raises GatewayError."""
        if not self.is_configured(self.gateway):
            raise GatewayError("Fill in the required credentials first.")
        return "Settings look complete. Place a test order to confirm the full flow."

    # --- flow ----------------------------------------------------------------
    def start(self, payment, return_url, cancel_url) -> Session:
        raise NotImplementedError

    def verify_return(self, data) -> bool:
        """Is the browser's return (redirect/POST) genuinely from the gateway?"""
        raise NotImplementedError

    def handle_return(self, payment, data) -> ReturnResult:
        """Default: tracker must match and the signature must verify (Safepay style)."""
        tracker = data.get("tracker") or data.get("beacon")
        ok = bool(tracker and tracker == payment.tracker and self.verify_return(data))
        if ok:
            return ReturnResult("paid", reference=data.get("reference") or data.get("ref") or "", verified=True)
        return ReturnResult("pending", reason="signature missing or invalid" if data.get("sig") else "")

    def parse_webhook(self, body: bytes, headers) -> WebhookResult:
        raise NotImplementedError
