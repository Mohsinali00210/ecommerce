# Orders, payments, backups & customer security

## Upgrade
```bash
pip install -r requirements.txt
python manage.py migrate            # payments app, store settings, backups, unseen badges
python manage.py collectstatic --noinput
# keep the worker + beat running (see COURIERS_SETUP.md): emails, payment expiry and scheduled backups use them
```
Make sure `private_media/` and `backups/` are **not** served by nginx (only `media/` and `static/` should be).

## Order emails
* **Order placed**: confirmation to the customer (COD / bank transfer at once; online payments once
  paid) and a "new order" email to `ADMIN_EMAIL`. Both are sent in the background, so checkout no
  longer waits for the mail server.
* **Status changed**: one email per change, with a progress bar and the courier tracking number. Choose
  which statuses email in **Store settings**. Courier updates no longer send a second, duplicate email.
* Every email links to `/order/view/<signed token>/`: a private order page that works without
  signing in. It expires after 180 days, can't be altered to show another order, hides the street
  address, and the signed-in owner is sent to the full account page.

## Payments
**Store settings → Payments**
* **Online payments** master switch: off = not offered at checkout *and* refused by the server.
* Cash on delivery (optional maximum order total), bank transfer (your account details are shown to
  the customer, who uploads the receipt).
* Unpaid online orders are cancelled and their stock released after N minutes (default 60).

**Safepay** (Payments → Safepay settings): paste the sandbox keys, tick *Use Safepay*, add the
webhook URL shown there in the Safepay dashboard, then switch *Online payments* on. Customers pay on
Safepay's page (card / JazzCash / Easypaisa). A payment is only marked paid when Safepay's signature
checks out (HMAC on the return, HMAC-SHA512 on webhooks). Duplicate notifications are ignored.

**Admin → Payments**: every attempt with filters, bank receipts to review, *mark paid* (with
reference), *reject receipt*, *record refund*, and a full history per payment.

Checkout fix: the page used to save every order as COD whatever the customer chose. It now sends the
chosen method, and only the methods you've enabled are shown.

## Sidebar badges
Every section shows how many new items arrived since **you** last opened it: return requests,
payments, tickets, product messages, questions, reviews, withdrawals, wish-to-buy and customers. The
group headers show totals. Yellow badges are things still waiting for action (open requests, receipts to
review, shipments needing attention). They don't clear until handled. Badges refresh every minute.
New page: **Sales → Return requests** (approve / reject with a comment).

## Backups (super admins only)
**System → Backups**
* *Back up now* (with or without images), *Import* a backup file, *Download*, *Restore*, *Delete*.
* **Download and restore need a 6-digit code emailed to you** (valid 10 minutes, 5 tries). The
  unlock lasts 10 minutes in that browser only. Restore also needs you to type RESTORE, and each code
  works for one restore.
* Restore checks the file (checksum, format, site version), **makes a safety backup first**, and
  replaces everything in one transaction: if anything fails, nothing changes. Everyone is signed out.
* **Automatic daily backups**: turn them on in Store settings (hour, how many to keep, images or not).
* Command line / cron: `python manage.py backup_db [--no-media]` and `python manage.py restore_db <file.zip>`.
  Files live in `BACKUP_DIR`; copy them off the server
  regularly (another disk / cloud storage).

## Customer panel security
* Uploads (contact form, return requests, profile picture, bank receipts) are checked by their
  actual bytes: images and PDFs only, with size limits. HTML/SVG files can no longer be uploaded.
* Bank receipts are stored outside the public media folder and served only to the owner and staff.
* Rate limits: registration, contact form, newsletter, reviews, questions, order tracking and the
  private order link.
* A return request can only include items from that order (it accepted any item before).
* Signing out wipes the shop's API tokens from the browser.
* New **Change password** page in the account area.
* Fixed: order tracking crashed with a server error for unknown order numbers.

## Tests
`python manage.py test couriers adminpanel payments` (103 tests).
