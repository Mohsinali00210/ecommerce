"""
Leopards Courier (LCS) merchant API.

Base URLs (set on the CourierProvider row):
  live:    https://merchantapi.leopardscourier.com/api/
  sandbox: https://merchantapistaging.leopardscourier.com/api/

Endpoints used: bookPacket, trackBookedPacket, cancelBookedPackets,
getAllCities, getTariffDetails  (all under <base>/<name>/format/json/)

Every response has "status": 1 on success, or "status": 0 with "error".

Optional credential.extra settings (JSON):
  {"request_format": "form"}   send form fields instead of JSON (default "json")
  {"origin_city_id": "789"}    force the origin city id instead of looking it up
  {"use_account_shipper": true} send "self" for shipper fields so Leopards uses
                                the details saved on your LCS account
"""
from decimal import Decimal, ROUND_HALF_UP

from . import register
from .base import (BaseCourierAdapter, BookingResult, CityData, CourierError,
                   TrackingEvent, TrackingUpdate, first, parse_dt)


def _int_amount(value):
    return int(Decimal(value or 0).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _error_text(data):
    err = data.get("error") if isinstance(data, dict) else None
    if isinstance(err, dict):
        return "; ".join(f"{k}: {v}" for k, v in err.items())
    if isinstance(err, list):
        return "; ".join(str(e) for e in err)
    return str(err or "Unknown error from Leopards")


@register("leopards")
class LeopardsAdapter(BaseCourierAdapter):
    display_name = "Leopards Courier (LCS)"
    supports_webhook = True   # endpoint is ready; LCS must enable push on your account

    # -- low level ----------------------------------------------------------
    def _auth(self):
        cred = self.require_credential()
        if not cred.api_key or not cred.api_password:
            raise CourierError("Leopards API key / password missing in courier settings.")
        return {"api_key": cred.api_key, "api_password": cred.api_password}

    def _extra(self, key, default=None):
        return (self.credential.extra or {}).get(key, default) if self.credential else default

    def _call(self, name, payload=None, method="POST"):
        body = {**self._auth(), **(payload or {})}
        path = f"{name}/format/json/"
        if method == "GET":
            data = self.http("GET", path, params=body)
        elif self._extra("request_format", "json") == "form":
            data = self.http("POST", path, data=body)
        else:
            data = self.http("POST", path, json=body)
        if not isinstance(data, dict):
            raise CourierError("Unexpected response from Leopards.", {"body": data})
        if str(data.get("status")) != "1":
            raise CourierError(_error_text(data), data)
        return data

    # -- operations ---------------------------------------------------------
    def book(self, req):
        if not req.consignee.city_id:
            raise CourierError(f"Destination city '{req.consignee.city_name}' is not mapped to a "
                               f"Leopards city. Pick the city on the booking form.")
        origin = self._extra("origin_city_id") or req.shipper.city_id or "self"
        use_self = bool(self._extra("use_account_shipper", False))

        payload = {
            "booked_packet_weight": int(req.weight_grams),
            "booked_packet_no_piece": int(req.pieces),
            "booked_packet_collect_amount": _int_amount(req.cod_amount),
            "booked_packet_order_id": req.reference,
            "origin_city": origin,
            "destination_city": req.consignee.city_id,
            # Shipper (you)
            "shipment_name_eng": "self" if use_self else req.shipper.name,
            "shipment_email": "self" if use_self else (req.shipper.email or "self"),
            "shipment_phone": "self" if use_self else req.shipper.phone,
            "shipment_address": "self" if use_self else req.shipper.address,
            # Consignee (customer)
            "consignment_name_eng": req.consignee.name,
            "consignment_email": req.consignee.email or "",
            "consignment_phone": req.consignee.phone,
            "consignment_address": req.consignee.address,
            # Packet
            "special_instructions": (req.special_instructions or req.description)[:250],
            "shipment_type": req.shipment_type or self.provider.default_shipment_type or "",
            # Returns go back to you
            "return_address": req.returns.address,
        }
        if req.returns.city_id:
            payload["return_city"] = req.returns.city_id
        # Description travels in custom data so it shows on the slip / portal
        if self._extra("request_format", "json") == "json":
            payload["custom_data"] = [{"description": req.description[:250]}]
        payload = {k: v for k, v in payload.items() if v not in (None, "")}

        data = self._call("bookPacket", payload)
        cn = first(data, "track_number", "cn_number")
        if not cn:
            raise CourierError("Leopards did not return a tracking number.", data)
        return BookingResult(tracking_number=str(cn), slip_url=str(data.get("slip_link") or ""),
                             raw=data, request=self.scrub(payload))

    def track(self, tracking_numbers):
        cns = [str(c) for c in tracking_numbers if c]
        if not cns:
            return {}
        data = self._call("trackBookedPacket", {"track_numbers": ",".join(cns)})
        results = {}
        for pkt in data.get("packet_list") or []:
            cn = str(first(pkt, "track_number", "cn_number") or "")
            if not cn:
                continue
            details = (pkt.get("Tracking Detail") or pkt.get("tracking_detail")
                       or pkt.get("Tracking_Detail") or [])
            events = []
            for d in details if isinstance(details, list) else []:
                st = first(d, "Status", "status")
                if not st:
                    continue
                events.append(TrackingEvent(
                    raw_status=str(st),
                    event_time=parse_dt(first(d, "Activity_datetime", "Activity_Date", "activity_date",
                                              "datetime")),
                    description=str(first(d, "Reason", "reason", "Receiver_Name") or ""),
                    location=str(first(d, "Origin", "location", "Station") or ""),
                ))
            events.sort(key=lambda e: (e.event_time is None, e.event_time))
            current = first(pkt, "booked_packet_status", "status") or (events[-1].raw_status if events else "")
            results[cn] = TrackingUpdate(tracking_number=cn, raw_status=str(current or ""),
                                         events=events, raw=pkt)
        return results

    def cancel(self, tracking_numbers):
        cns = [str(c) for c in tracking_numbers if c]
        data = self._call("cancelBookedPackets", {"cn_numbers": ",".join(cns)})
        return {cn: True for cn in cns} | {"_raw": data}

    def get_cities(self):
        data = self._call("getAllCities")
        cities = []
        for c in data.get("city_list") or []:
            cid = first(c, "id", "city_id")
            name = first(c, "name", "city_name")
            if cid is None or not name:
                continue
            cities.append(CityData(
                external_id=str(cid), name=str(name).strip(),
                allow_origin=str(c.get("allow_as_origin", "1")).lower() in ("1", "true", "yes"),
                allow_destination=str(c.get("allow_as_destination", "1")).lower() in ("1", "true", "yes"),
            ))
        return cities

    def get_tariff(self, weight_grams, origin_city_id, destination_city_id, cod_amount):
        data = self._call("getTariffDetails", {
            "packet_weight": int(weight_grams),
            "shipment_type": self.provider.default_shipment_type or "overnight",
            "origin_city": origin_city_id or "self",
            "destination_city": destination_city_id,
            "cod_amount": _int_amount(cod_amount) or 1,
        }, method="GET")
        return data
