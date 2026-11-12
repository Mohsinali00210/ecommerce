# Courier integration (Leopards) + security update

## 1. Before you deploy: secrets

The old `settings.py` had the Django `SECRET_KEY` and the Hostinger SMTP password
hardcoded, and the project zip included `.env`. Treat them as leaked:

1. **Change the Hostinger mailbox password** for `admin@shanzee.com`.
2. **Change the PostgreSQL password** if it was the one in the old `.env`.
3. Copy `.env.example` to `.env` and fill in every value (new `DJANGO_SECRET_KEY`,
   new `SMTP_PASSWORD`, `DB_PASSWORD`, `COURIER_ENCRYPTION_KEY`).
   settings.py now reads **only** the names in `.env.example`; the old keys are ignored.
4. A new `DJANGO_SECRET_KEY` logs everyone out once. That's expected.

## 2. Install

```bash
pip install -r requirements.txt          # adds celery
sudo apt install redis-server            # or use a managed Redis
python manage.py migrate                 # adds couriers tables + new order statuses
python manage.py collectstatic --noinput
```

Run these processes (systemd or supervisor in production):

```bash
daphne -b 127.0.0.1 -p 8000 shanzeeecommerce.asgi:application     # web (as before)
celery -A shanzeeecommerce worker -l info                          # booking, emails, webhooks
celery -A shanzeeecommerce beat -l info                            # tracking every 30 min, weekly city sync
```

Without `REDIS_URL` the tasks run inline. That's fine for local development, but don't run production that way.

## 3. Connect Leopards (5 minutes)

Admin panel → **Shipping → Courier settings**:

1. **Leopards Courier** is already there (sandbox mode). Click **Add credentials**,
   choose *Sandbox*, and paste your API key + API password (from the LCS merchant portal → API).
2. Click **Test connection**, then **Sync cities** (downloads the Leopards city list + ids).
3. Under **Pickup & return details** add your store address and, if different, the
   address returned parcels should come back to. This is sent with every booking.
4. Book one test order. When it works: **Add credentials** again with environment *Live*,
   then **Edit** Leopards → Environment = *Live*.

Or from the shell:
```bash
python manage.py courier_setup leopards --env live --key KEY --password PASS --use \
  --shipper-name "Shan Zee" --shipper-phone 03xxxxxxxxx --shipper-address "..." --shipper-city Lahore
python manage.py courier_sync_cities leopards
```

## 4. Booking

* **Manual:** Orders list → truck icon → booking form, pre-filled with the customer's name,
  phone, address and city, the weight (product weight × qty, or the courier default),
  pieces, the packet description built from the items, and COD = order total for COD
  orders (0 for prepaid). Edit anything, then click **Book**. You get the CN number, the slip link, and a
  customer notification + email.
* **Bulk:** Shipping → Shipments & booking → tick orders → **Book selected**.
* **Automatic:** Edit Leopards → tick *Auto book enabled* and set the trigger status (default
  `processing`) and payment methods (default `cod`). When an order reaches that status, a
  Celery task books it. If the city can't be matched, the order stays in "ready to book" so you
  can book it by hand.

A failed booking is saved with the courier's error message, and you can retry. An order can only have one
live shipment. Cancel it (this also cancels it with Leopards) to re-book.

## 5. Status updates (callbacks / webhooks)

Two ways, both enabled:

* **Polling (always works):** every `COURIER_POLL_MINUTES` (30) Celery calls
  `trackBookedPacket` for all unfinished shipments, saves every scan, and moves the order.
* **Webhook / callback URL:** shown per credential in Courier settings, e.g.
  `https://shanzee.com/couriers/webhook/leopards/<secret-token>/`. Give it to Leopards
  (ask your LCS account manager to enable status push to this URL). JSON and form posts are both
  accepted (`track_number`/`cn_number` + `status`/`booked_packet_status`). Every call is
  logged under *Recent webhook calls*. Rotate the token any time.
  Optional IP allow-list: set credential *Extra* to `{"webhook_allowed_ips": ["1.2.3.0/24"]}`.

**Status mapping** (Courier settings, right side) turns courier wording into our statuses:
Booked → *booked*, Picked/Dispatched/Arrived → *shipped*, Assigned to courier → *out for delivery*,
Delivered → *delivered*, Being return → *returning*, Returned to shipper → *returned* (stock goes back
automatically), Undelivered/Refused/Pending → *delivery failed* (the order is left alone). Any status
with no rule is flagged **unmapped** with a one-click "Map it" link, so nothing gets lost.

Customers see the courier, the CN number, and the full scan history on `/track-order/` and in their emails.
The address field suggests Leopards city names, so cities match at booking time.

## 6. Adding another courier

* **No API (or not yet):** Courier settings → Add courier → adapter *Manual*. Staff type the CN
  number when booking. Status comes from the webhook (if the courier can call one) or is set by hand.
* **With an API:** copy `couriers/adapters/leopards.py` to e.g. `tcs.py`, implement `book`,
  `track`, `cancel`, `get_cities` for that API, register it with `@register("tcs")`, import it in
  `couriers/adapters/__init__.py`, then add the provider row + credentials in the panel.
  Booking screens, auto-booking, polling, webhooks, status mapping and notifications all work
  without other changes.

## 7. Leopards API notes (verify against your LCS API document)

* Base URLs: live `https://merchantapi.leopardscourier.com/api/`, staging
  `https://merchantapistaging.leopardscourier.com/api/` (editable on the provider).
* Requests are JSON by default. If your account needs form posts, set credential *Extra* to
  `{"request_format": "form"}`.
* `{"use_account_shipper": true}` sends `self` for the shipper fields so LCS uses the details on your
  LCS account. `{"origin_city_id": "789"}` forces the origin city id.
* Weight is sent in grams. Product `weight` is in kg.
* `default_shipment_type` is `overnight`. Change it on the provider if your account uses another
  service code.

## 8. Tests

```bash
python manage.py test couriers      # 38 tests: booking, tracking, webhooks, auto-book, security fixes
```
