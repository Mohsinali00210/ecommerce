# Shan Zee — UI modernisation (motion + flow)

## Install (2 steps)
1. Replace your `templates/` folder with the one in this zip (only `base2.html`, `home/index.html`, `home/cart.html`,
   `home/checkout.html`, `home/partials/product_card.html` changed — everything else is untouched).
2. Copy `static/css/modern.css` and `static/js/modern.js` into your Django `static/css/` and `static/js/` folders,
   then run `python manage.py collectstatic` if you deploy with it. `base2.html` already links both files.

## New UI / motion (global — applies to every page that extends base2.html)
- Sticky glass header that shrinks on scroll, secondary nav hides on scroll-down / returns on scroll-up, animated nav underlines
- Scroll-progress bar, back-to-top button with progress ring, soft page fade between pages
- Scroll-reveal with automatic stagger (sections, product grids, trust badges, blog/order/address cards)
- Product cards: lift + image zoom, second-image crossfade, floating quick-view/wishlist buttons, **quick “Add to cart” bar**,
  shimmer skeleton while images load, pop animation on the wishlist heart, subtle 3-D tilt (desktop only)
- Home: staggered hero text, Ken-Burns hero image, animated slide indicators, marquee strip (shipping/COD/returns), animated section titles
- Buttons: shine sweep, ripple, loading spinner. Modals: blur backdrop + spring entrance. Inputs: brass focus glow
- Toasts replace the old alert helpers (`showToast` / `showAlert` still work, now styled)
- `prefers-reduced-motion` is respected everywhere

## Flow changes
1. **Add to cart no longer feels like a dead end** — product flies into the cart icon, a slide-in “Added to your cart” drawer shows the
   item, a free-shipping progress bar, and **View cart & checkout / Continue shopping**. Works for the card quick-add, quick-view and product page
   (it wraps `Cart.add`, so no changes needed in those templates). Products with several variants open Quick View instead of guessing a variant.
2. **Cart page**: 3-step progress (Cart → Details → Confirmation), tidy “select all” bar, animated item removal, live free-shipping meter
   (threshold PKR 3,500 — change `FREE_SHIP` in modern.js), sticky order summary, loading state on “Proceed to Checkout”.
3. **Checkout**: sticky summary, validation scrolls to the first bad field, double-submit guard + spinner on “Place Order”, panels animate in.
4. **Mobile**: bottom navigation (Home · Browse · Search · Cart · Saved) with live badges.

## Bugs fixed while in there
- `index.html`: a script fired a *toggle* wishlist request for every product on every page load (and used `btn.dataset.wishlist-btn`, which evaluates to `NaN`). Removed — heart state already comes from the server.
- `index.html`: duplicate `#quickViewModal` (already in base2) removed.
- `cart.html`: loaded `assets/js/cart.js` + `assets/js/app.js` from a relative path (404 on every cart load) — removed; “Continue shopping” pointed to `shop.html` — now goes Home.
- `checkout.html`: second `<header class="site-header">` nested under the main header — now `checkout-subheader` so it doesn't become a second sticky header.
- `base2.html`: relative links (`new-arrivals`, `user-profile`, `best-sellers`, `profile.html`) resolved against the *current* URL, so they broke on any page except `/`. Now root-relative — **confirm these four paths match your urls.py** (I couldn't see it).

## Things to verify on your side
- The drawer reads success from `Cart.add`'s return value (a Promise resolving to anything except `{success:false}` counts as success). If your cart.js returns something else, tell me and I'll adapt it.
- For an accurate free-shipping meter in the drawer, add `cart_total` to the JSON returned by `home:header-counts` (it is read as `HeaderCounts.total`); otherwise it uses the added item's value.
- `store/*.html` are placeholder stubs extending a `base.html` that wasn't in the archive; I left them alone.

---
## Round 2 — section-wise colours + stylish finish (`static/css/theme.css`)
Copy `theme.css` next to `modern.css` (base2.html already links it). All colours are tokens (`--sec`, `--sec-deep`, `--sec-soft`) at the top of the file.

| Section / page | Palette |
|---|---|
| Top bar, nav strip | forest-green gradient, gold "All Categories", terracotta "Find Best Deal" pill |
| Hero | green→gold overlay, glowing eyebrow pill, gradient headline |
| Marquee | animated gold band |
| Categories | warm sand |
| Trust badges | sage green card with emerald icons |
| Featured tab | emerald · **New Arrivals tab turns terracotta** · Best Sellers tab plum (automatic via `:has()`) |
| Newsletter | deep emerald mesh with gold glow |
| Footer | dark forest, gold headings, gold hairline |
| Orders / Wallet / Wishlist / Contact / Blog / Best-deals | slate / gold / rose / teal / plum / terracotta page banner, breadcrumbs, tables, buttons and cards (set by `body[data-page=<url name>]`) |
| Cart, Checkout, Profile, Addresses | emerald with gold CTA |

Also: gradient buttons with glow, pill tabs, gradient headings, gradient hairline on product-card hover, branded scrollbar, branded toasts/drawer.
`base2.html` now sets `data-page="{{ request.resolver_match.url_name }}"` on `<body>`; if your url names differ, edit the `body[data-page="…"]` rules at the top of theme.css.
