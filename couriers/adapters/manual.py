"""
Manual courier: for couriers without an API (or while waiting for API access).
Staff enter the tracking number themselves; status updates arrive via the
webhook (if the courier can call one) or are set manually in the shipment page.
"""
from .base import BaseCourierAdapter, BookingResult, CourierError, NotSupported
from . import register


@register("manual")
class ManualAdapter(BaseCourierAdapter):
    display_name = "Manual (no API)"
    supports_api_booking = False
    supports_tracking = False
    supports_cancel = False
    supports_cities = False

    def book(self, req):
        if not req.tracking_number:
            raise CourierError("Enter the tracking / CN number given by the courier.")
        return BookingResult(tracking_number=req.tracking_number.strip(), raw={"manual": True},
                             request={"reference": req.reference})

    def cancel(self, tracking_numbers):
        # Nothing to call - the shipment is simply marked cancelled locally.
        return {cn: True for cn in tracking_numbers}

    def test_connection(self):
        raise NotSupported("Manual couriers have no API to test.")
