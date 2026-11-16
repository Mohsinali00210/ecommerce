from dataclasses import dataclass, field


class GatewayError(Exception):
    def __init__(self, message, data=None):
        super().__init__(message)
        self.data = data or {}


@dataclass
class Session:
    tracker: str
    redirect_url: str
    raw: dict = field(default_factory=dict)


@dataclass
class WebhookResult:
    event: str              # "paid", "failed" or "ignored"
    tracker: str = ""
    reference: str = ""
    raw: dict = field(default_factory=dict)


class BaseGateway:
    code = ""
    display_name = ""
    timeout = 25

    def __init__(self, gateway):
        self.gateway = gateway

    def start(self, payment, return_url, cancel_url) -> Session:
        raise NotImplementedError

    def verify_return(self, data) -> bool:
        """Is the browser's return (redirect/POST) genuinely from the gateway?"""
        raise NotImplementedError

    def parse_webhook(self, body: bytes, headers) -> WebhookResult:
        raise NotImplementedError
