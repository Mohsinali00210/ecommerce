"""
Courier adapter contract.

To add a courier with a new API:
  1. Create couriers/adapters/<name>.py with a class extending BaseCourierAdapter.
  2. Decorate it with @register("<name>") and implement the methods it supports.
  3. Import it in couriers/adapters/__init__.py.
  4. In the admin panel add a CourierProvider with adapter="<name>" and its credentials.
Everything else (booking screens, auto-booking, polling, webhooks, notifications) works unchanged.
"""
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Optional

import requests


class CourierError(Exception):
    """Raised when the courier rejects a request or can't be reached."""

    def __init__(self, message, response=None):
        super().__init__(message)
        self.response = response or {}


class NotSupported(CourierError):
    pass


@dataclass
class Party:
    name: str
    phone: str
    address: str
    city_name: str
    city_id: Optional[str] = None
    email: str = ""


@dataclass
class BookingRequest:
    reference: str               # our order number
    shipper: Party               # pickup
    returns: Party               # where returns go
    consignee: Party             # customer
    weight_grams: int
    pieces: int
    description: str
    cod_amount: Decimal
    special_instructions: str = ""
    shipment_type: str = ""
    tracking_number: str = ""    # used by the manual adapter only


@dataclass
class BookingResult:
    tracking_number: str
    slip_url: str = ""
    raw: dict = field(default_factory=dict)
    request: dict = field(default_factory=dict)  # payload sent (secrets removed)


@dataclass
class TrackingEvent:
    raw_status: str
    event_time: Optional[datetime] = None
    description: str = ""
    location: str = ""


@dataclass
class TrackingUpdate:
    tracking_number: str
    raw_status: str                       # current status text
    events: list = field(default_factory=list)  # list[TrackingEvent], oldest first
    raw: dict = field(default_factory=dict)


@dataclass
class CityData:
    external_id: str
    name: str
    allow_origin: bool = True
    allow_destination: bool = True


class BaseCourierAdapter:
    code = ""
    display_name = ""
    supports_api_booking = True
    supports_tracking = True
    supports_cancel = True
    supports_cities = True
    supports_webhook = True
    timeout = 30
    secret_fields = ("api_key", "api_password")

    def __init__(self, provider, credential):
        self.provider = provider
        self.credential = credential

    # -- helpers ----------------------------------------------------------
    def require_credential(self):
        if not self.credential:
            raise CourierError(
                f"No active {self.provider.get_environment_display()} credential for "
                f"{self.provider.name}. Add one in Couriers > Settings.")
        return self.credential

    def scrub(self, payload):
        return {k: ("***" if k in self.secret_fields else v) for k, v in payload.items()}

    def http(self, method, path, **kwargs):
        base = (self.provider.base_url or "").rstrip("/") + "/"
        url = base + path.lstrip("/")
        try:
            resp = requests.request(method, url, timeout=self.timeout, **kwargs)
        except requests.RequestException as exc:
            raise CourierError(f"Could not reach {self.provider.name}: {exc}")
        try:
            data = resp.json()
        except ValueError:
            raise CourierError(
                f"{self.provider.name} returned a non-JSON response (HTTP {resp.status_code}).",
                {"body": resp.text[:2000]})
        if resp.status_code >= 400:
            raise CourierError(f"{self.provider.name} HTTP {resp.status_code}", data)
        return data

    # -- operations (override what the courier supports) --------------------
    def book(self, req: BookingRequest) -> BookingResult:
        raise NotSupported("Booking is not supported by this courier.")

    def track(self, tracking_numbers) -> dict:
        """Return {tracking_number: TrackingUpdate}."""
        raise NotSupported("Tracking is not supported by this courier.")

    def cancel(self, tracking_numbers) -> dict:
        raise NotSupported("Cancellation is not supported by this courier.")

    def get_cities(self) -> list:
        raise NotSupported("City list is not supported by this courier.")

    def get_tariff(self, weight_grams, origin_city_id, destination_city_id, cod_amount):
        raise NotSupported("Tariff lookup is not supported by this courier.")

    def test_connection(self):
        """Cheap authenticated call used by the 'Test connection' button."""
        cities = self.get_cities()
        return f"Connected. {len(cities)} cities available."

    def parse_webhook(self, data: dict, headers: dict) -> list:
        """Turn a webhook body into a list of TrackingUpdate.

        Default parser accepts the common shapes:
          {"track_number": "...", "status": "..."}
          {"cn_number": "...", "booked_packet_status": "...", "activity_date": "..."}
          {"data": [ ...same objects... ]} / [ ... ]
        """
        items = data
        if isinstance(data, dict):
            items = data.get("data") or data.get("packets") or data.get("packet_list") or [data]
        if isinstance(items, dict):
            items = [items]
        updates = []
        for item in items or []:
            if not isinstance(item, dict):
                continue
            cn = first(item, "track_number", "tracking_number", "cn_number", "cn", "consignment_no")
            status = first(item, "status", "booked_packet_status", "current_status", "Status")
            if not cn or not status:
                continue
            when = parse_dt(first(item, "activity_datetime", "activity_date", "datetime",
                                  "status_date", "updated_at", "Activity_datetime"))
            ev = TrackingEvent(raw_status=str(status), event_time=when,
                               description=str(first(item, "reason", "remarks", "Reason") or ""),
                               location=str(first(item, "location", "city", "station") or ""))
            updates.append(TrackingUpdate(tracking_number=str(cn), raw_status=str(status),
                                          events=[ev], raw=item))
        return updates


def first(d, *keys):
    for k in keys:
        v = d.get(k)
        if v not in (None, "", []):
            return v
    return None


_DT_FORMATS = ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M", "%d-%m-%Y %H:%M:%S",
               "%d/%m/%Y %H:%M:%S", "%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%b %d, %Y %I:%M %p",
               "%d %b %Y %I:%M %p")


def parse_dt(value):
    """Best-effort parse of courier dates; returns aware datetime or None."""
    from django.utils import timezone
    if not value:
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        s = str(value).strip().replace("Z", "")
        dt = None
        try:
            dt = datetime.fromisoformat(s)
        except ValueError:
            for fmt in _DT_FORMATS:
                try:
                    dt = datetime.strptime(s, fmt)
                    break
                except ValueError:
                    continue
        if dt is None:
            return None
    if timezone.is_naive(dt):
        # Pakistani couriers send local time
        from zoneinfo import ZoneInfo
        dt = dt.replace(tzinfo=ZoneInfo("Asia/Karachi"))
    return dt
