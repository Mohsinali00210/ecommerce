# Admin panel: what changed

## Upgrade steps
```bash
pip install -r requirements.txt
python manage.py migrate          # error-log columns, SecurityEvent table, role groups
python manage.py collectstatic --noinput
```
Add the new variables from `.env.example` (all optional, with sensible defaults).

**Roles:** super admins keep full access. Any other staff account has **no access until you
give it a role** in *System → Team & roles*. Roles: Administrator, Store Manager, Catalog
Manager, Order Manager, Support Agent, Analyst. The URL → permission map is in
`accounts/rbac.py` (`ADMIN_RULES`): one place, enforced by middleware for every admin page
and API.

## Categories (fixed)
* **Edit didn't load / saved a new category.** The edit button passed the whole category as
  JSON inside a single-quoted `onclick`, so any name with an apostrophe (Men's…) broke it.
  The modal then opened empty and Save sent a POST. Also, a previously opened
  sub-category dialog left a parent id behind that later edits picked up.
* **Explore** now drills down any number of levels with breadcrumbs, shows real
  sub-category counts, and lets you add, edit and delete at every level.
* Delete asks for confirmation, actually authenticates (it used an undefined token),
  soft-deletes the whole branch, and refreshes the list.
* API: duplicate names under the same parent are rejected with a clear message, a category
  can't be moved under its own child, images are limited to JPG/PNG/WEBP/GIF up to 2 MB, and
  re-creating a deleted name works (it used to crash).

## Sessions
* A live countdown in the top bar shows the time left. Click it to extend.
* A "Still there?" dialog appears 2 minutes before sign-out, with *Stay signed in* and *Sign out*.
* Idle timeout: 60 min by default. Mouse, keyboard and page use count as activity;
  background polling doesn't, so an unattended tab still signs out.
* Absolute limit: 12 h. Staff sessions also **end when the browser closes**.
* Tabs stay in sync (extending in one tab extends all; signing out signs out all).
* The admin API token is short-lived (15 min), kept in `sessionStorage` (gone when the
  browser closes), and refreshed automatically. No long-lived refresh token is stored.
* Logging in from the login page now goes to the dashboard (it used to send you back to
  the login page) and honours `?next=`.

## Dashboard
KPI cards (revenue, orders, avg. order value, items sold, new customers, cancel/return rate,
each compared with the previous period), a store snapshot, and charts: revenue & orders
trend, orders by status, top products, sales by category, payment methods, new customers,
and orders by hour. It also lists recent orders, low stock and recent activity. Date range:
presets or custom dates.

## Security
* Role-based access (above), plus the CSRF failure page, secure session cookies (HttpOnly,
  SameSite) and logout as a POST.
* Every admin request and failure is audited (see Logs).
* Front-end libraries are self-hosted (`adminpanel/static/adminpanel/vendor`), so the admin
  loads no third-party scripts.

## Errors & logging
* Friendly 400/403/404/500, "page expired" (CSRF) and "too many attempts" pages with a
  reference code. API errors return `{"detail": ..., "reference": ...}`, never a stack trace.
* Toasts for success and failure, and confirmation dialogs for destructive actions.
  Old inline `confirm()` buttons are upgraded automatically, and `data-confirm="…"` works
  on any link, button or form.
* `logs/app.log`, `logs/error.log` and `logs/security.log` are JSON lines with timestamp,
  severity, request id, user, IP, path, method and exception. Secrets are masked. The same
  data goes to the `ErrorLog` and `SecurityEvent` tables, browsable under *System → Logs & audit*.

## Tests
`python manage.py test adminpanel couriers` (78 tests).
