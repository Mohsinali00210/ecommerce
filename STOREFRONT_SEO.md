# Storefront, free shipping & SEO

## After uploading
```bash
pip install -r requirements.txt
python manage.py migrate        # adds shipping settings, home features (seeded with your 4 tiles), SEO tables
```
`.env` must have your real domain: `SITE_URL=https://shanzee.com`. Sitemap, feed, canonical links and webhook links all use it.

## What's new in the admin panel
| Page | Where | Who |
|---|---|---|
| Home page features | Marketing → Home page features | view: catalog roles, edit: `manage_marketing` |
| SEO & search engines | Marketing → SEO & search engines | `manage_marketing` |
| Shipping rules | System → Store settings → Shipping | `manage_settings` |
| Webhook URL edit | Shipping → Courier settings → credential → Edit | `manage_shipping` |

### Free shipping
Store settings → Shipping: **free shipping from Rs 3,500** (after discounts) and **max shipping Rs 450 per order** (0 = no cap).
The same rule (adminpanel/shipping.py) is used by the cart, checkout, **order placement on the server**, product page, quick view,
the home tile (`{threshold}`) and the Google feed. Before this the cart only *displayed* a 3,500 goal; it was never applied.

### Webhook URL
Each courier credential has an editable **Webhook token** (16-64 letters/digits/-/_) with a live preview, a copy button and "New token".
Empty = keep the current one. Optional per-courier **Webhook site address** overrides SITE_URL in the link.

## Public SEO URLs
| URL | Purpose |
|---|---|
| `/sitemap.xml` | index → `/sitemap-pages.xml`, `-products`, `-categories`, `-blog` |
| `/robots.txt` | blocks admin, account, cart, checkout, filter URLs; points to the sitemap |
| `/feeds/google-merchant.xml` | Google Merchant Center product feed (products with a photo) |
| `/<indexnow-key>.txt` | IndexNow key file |

Every storefront page now gets: a unique `<title>`, meta description, canonical link, robots tag, Open Graph + Twitter tags,
and JSON-LD (Organization + WebSite search box on home; Product with price, stock, shipping, returns and rating + breadcrumbs on
products; BlogPosting on posts). Search/filter pages and private pages are `noindex`.

---

## 1. Google Search Console
1. Go to search.google.com/search-console → **Add property** → **URL prefix** → `https://shanzee.com`.
2. Choose **HTML tag**, copy the tag, paste it (whole tag is fine) into *SEO → Google site verification*, **Save**, then click **Verify** in Google.
3. **Sitemaps** → enter `sitemap.xml` → Submit.
4. **URL inspection** → paste your home page → **Request indexing**. Repeat for 5-10 key products.
   (Domain-property verification via DNS TXT also works — add the TXT record at your domain registrar instead.)

## 2. Bing Webmaster Tools
Fastest: bing.com/webmasters → **Import from Google Search Console** (takes sites and sitemaps across).
Or add the site manually → **HTML Meta tag** → paste into *SEO → Bing site verification* → Save → Verify → submit `https://shanzee.com/sitemap.xml`.

## 3. IndexNow (instant indexing: Bing, Yandex, Seznam, Naver, Yep)
Turn on *SEO → IndexNow* and Save. Open the key file link on the page to check it loads. Then click **Send all pages to IndexNow** once.
From then on every new/changed product or blog post is sent automatically (same URL at most once per 10 min). Results appear in the Indexing log.

## 4. Google Indexing API (optional)
1. console.cloud.google.com → new project → enable **Web Search Indexing API**.
2. IAM → Service accounts → create one → Keys → **Add key → JSON** → download.
3. Search Console → Settings → Users and permissions → add the service account e-mail as **Owner**.
4. Paste the JSON into *SEO → Service account JSON key*, tick Google Indexing API, Save, click **Test Google key**.
Note: Google officially supports this API only for job-posting and live-stream pages and allows 200 URLs/day. For products the
sitemap + Search Console is the reliable route; treat this as a bonus.

## 5. Google listing (getting the shop onto Google)
**a) Google Business Profile** — your shop on Google Maps / Search with phone, hours, reviews.
business.google.com → add business "Shan Zee" → category e.g. *Clothing store* / *Online retailer* → if you have no walk-in shop,
choose **"I deliver goods and services to my customers"** and hide the address, set service area (Pakistan / cities) → verify
(postcard, phone or video) → add logo, cover photo, website `https://shanzee.com`, WhatsApp number, hours, products.
Ask happy customers for Google reviews (add the review link to the order-delivered email or WhatsApp).

**b) Google Merchant Center** — free product listings in Google Shopping, Images and Search.
1. merchants.google.com → create account, business name, country **Pakistan**, website `https://shanzee.com` → verify & claim the site
   (easiest: link the Search Console account you set up above).
2. Settings → **Shipping & returns**: add a Pakistan shipping service matching the shop (e.g. Rs 200, free over Rs 3,500, 2-5 days)
   and a **7-day return policy**. Add business phone and address.
3. Products → **Add products → Add from file → Enter a link to your file (scheduled fetch)** →
   `https://shanzee.com/feeds/google-merchant.xml`, daily. Currency PKR, language English.
4. Make sure the shop has visible **Contact, Return policy, Privacy policy and Terms** pages and correct prices — Merchant
   Center rejects stores without them. Fix any item issues it reports (usually photos or missing details).
5. Under **Growth → Manage programs** turn on **Free listings**.

**c) Fill in SEO → Business details** (logo, phone, address, social links) — this feeds Google's knowledge panel and rich results.
Check product pages with search.google.com/test/rich-results.

## Tips
- Give every product a clear name, a 150-300 word description and good photos; set Meta title/description in the product editor for top sellers.
- Write blog posts (styling guides, size guides) and link to products — they bring search traffic.
- Keep "Hide the whole site from search engines" **off** on the live shop.
