# Weight shipping, payment gateways, payouts & Google Merchant API

## Upgrade
```bash
pip install -r requirements.txt          # nothing new to install
python manage.py migrate                 # tariffs + Leopards seed, gateways, payout methods, merchant fields
python manage.py test payments.tests.test_shipping_gateways_payouts
```
Keep the Celery worker running (Merchant API auto-sync and "send all" use it).

## 1. Weight-based shipping  (Admin > Shipping > Shipping rates)
* Seeded default tariff **Leopards Overnight - COD**:

  | Weight | Within city | Zone A (same province) | Zone B (other province) |
  |---|---|---|---|
  | 0 - 250 g | Rs 160 | Rs 180 | Rs 200 |
  | 250 - 500 g | Rs 180 | Rs 200 | Rs 230 |
  | 500 g - 1 kg | Rs 180 | Rs 230 | Rs 250 |

  Heavier parcels: 1 kg price + "extra per step" (per 500 g). **The extras are 0 until you set them.**
* Set **Ships from** (origin city / province) on the tariff, or it uses the default pickup address city.
* Applies to items that are **not** marked free shipping and have a **weight** (Product > weight, kg).
  All weighed items in the order go in one parcel. Items with no weight keep their flat shipping charge.
* Order: free item → nothing; free-shipping threshold (if on and reached) → free; else weight tariff + flat
  charges, capped at "Maximum shipping per order" (0 = no cap).
* Zone: same city → within city; same province → Zone A; anything else or unknown city → Zone B.
  The province comes from the address's state field, or from the city name (`couriers/tariffs.py`).
* Where it shows: product page and quick view (price for the customer's default address, plus a rates
  table), cart (estimate for the default address, or Zone B), checkout (updates when the address changes),
  order placement (server side), Google feed / JSON-LD / Merchant API (Zone B price, never too low).
* Switch: Store settings > Shipping > *Weight-based shipping*, or the button on the Shipping rates page.
  It is **on by default** after migrating.

## 2. Payment gateways  (Admin > Payment gateways)
Cash on delivery stays first and pre-selected. Each gateway that is switched on becomes its own choice
at checkout (`online:<code>`), and only when *Online payments* is on in Store settings.

| Gateway | Admin fields | Confirmed by |
|---|---|---|
| Safepay | API key, secret key, webhook secret | HMAC on return + signed webhook |
| JazzCash (hosted page v1.1) | Merchant ID, integrity salt, password | pp_SecureHash on return / IPN |
| Easypaisa (Easypay hosted) | Store ID, hash key, inquiry `username:password` | Inquire Transaction API (return is unsigned) |
| Stripe Checkout | secret key, webhook secret | server-side session check + signed webhook |
| Test gateway | none | signed simulator (staff only, or everyone in DEBUG) |

Each gateway page has **Test connection**, the webhook/IPN URL to paste in the provider dashboard and
sandbox/live switch. A pending online payment can be re-checked from Admin > Payments > payment >
*Check status* (Stripe, Easypaisa).

**Testing:** switch on the Test gateway + Online payments, sign in as staff, place an order, choose
*Test payment* and simulate success / failure / cancel. Then use each provider's sandbox credentials.

**Logs:** Admin > Payments > Logs shows every event (session started, return, webhook accepted/rejected,
status checks, staff actions, settings changes).

## 3. Wallet withdrawals  (Admin > Payout settings)
* Per method (JazzCash, Easypaisa, Bank, Stripe): on/off, **charge** (fixed + %, min, max), min/max amount,
  processing time. **Charges are seeded at 0: set your real charges.**
* Customer's withdraw page shows the charges table and a live "charge / you will receive" breakdown.
  The full amount is held from the wallet; the charge is kept; the rest is sent.
* Payout mode:
  * **Manual** (default): send the money yourself, then approve with the transaction reference.
  * **Automatic**: sent on approval via *Test payout* (sandbox; account numbers ending 0000 fail),
    *Stripe Connect transfer* (account number = `acct_...`) or *Generic payout API* (signed JSON POST to
    your payout service / bank middleware; contract in `UserPanel/payouts.py`).
    JazzCash / Easypaisa disbursement APIs require a business agreement; plug them in through the generic API.
* "Processing" replies stay open until staff confirm with *Confirm paid*.
* Logs: Admin > Withdrawals > Payout logs.

## 4. Transaction history
* Admin: **Transactions** (sidebar) - payments, wallet credits/debits, withdrawals for every customer.
* Customer: **Account > Transactions** (also in the header menu and mobile menu).

## 5. Google Merchant API  (Admin > Storefront > SEO > Google Merchant Center)
1. In Google Cloud enable the **Merchant API**; use the same service account JSON key as Google Indexing.
2. In Merchant Center add the service account e-mail as a user, then Settings > Data sources >
   *Add product source* > *Add products using API*; copy the data source ID.
3. Enter the account ID + data source ID, tick *Merchant API*, save, click **Test Merchant connection**,
   then **Send all products now**. With *auto-sync* on, saving a product sends it (or removes it when hidden).
4. **Preview API data** shows the exact JSON sent for a product. The XML feed keeps working.

## 6. Mobile
The mobile menu (hamburger) now has a *My Account* section with **Logout**; every account page sidebar
has Transactions and Logout.
