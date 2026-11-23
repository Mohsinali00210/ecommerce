"""Instant indexing: IndexNow (Bing, Yandex, Seznam, Naver, Yep) and the Google Indexing API.

IndexNow     https://www.indexnow.org/documentation
             POST https://api.indexnow.org/indexnow {host, key, keyLocation, urlList}
             The key file is served at /<key>.txt (storefront.public_views.indexnow_key).
Google       https://developers.google.com/search/apis/indexing-api/v3/quickstart
             POST https://indexing.googleapis.com/v3/urlNotifications:publish {url, type}
             Auth: OAuth2 service-account JWT (scope .../auth/indexing). The service
             account's e-mail must be added as an *Owner* in Search Console.
             Google officially supports this API only for JobPosting / BroadcastEvent pages;
             for products the sitemap + Search Console remain the main route.
"""
import base64
import json
import logging
import time
from urllib.parse import urlsplit

import requests
from django.core.cache import cache

from .models import IndexingLog, SeoSettings
from .seo import site_url

log = logging.getLogger("storefront.indexing")

INDEXNOW_ENDPOINT = "https://api.indexnow.org/indexnow"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_PUBLISH_URL = "https://indexing.googleapis.com/v3/urlNotifications:publish"
GOOGLE_SCOPE = "https://www.googleapis.com/auth/indexing"
TIMEOUT = 15


class IndexingError(Exception):
    pass


def _own_urls(urls):
    """Only URLs on our own public domain are ever submitted."""
    host = urlsplit(site_url()).netloc
    out = []
    for u in urls:
        if u and urlsplit(u).netloc == host and u not in out:
            out.append(u)
    return out


def _record(engine, urls, ok, code, message, action="updated", user=None):
    return IndexingLog.objects.create(engine=engine, urls=urls[:1000], ok=ok, status_code=code,
                                      message=(message or "")[:2000], action=action, created_by=user)


# ---------------------------------------------------------------------------
# IndexNow
# ---------------------------------------------------------------------------
INDEXNOW_CODES = {
    200: "Submitted.", 202: "Accepted — the key will be checked shortly.",
    400: "Bad request (invalid format).", 403: "Key not valid: the key file could not be read at /<key>.txt.",
    422: "URLs don't belong to the host, or the key doesn't match.", 429: "Too many requests — try later.",
}


def indexnow_submit(urls, user=None, force=False):
    s = SeoSettings.get()
    if not (s.indexnow_enabled or force):
        return None
    if s.hide_from_search_engines:
        return None
    urls = _own_urls(urls)
    if not urls:
        return None
    host = urlsplit(site_url()).netloc
    payload = {"host": host, "key": s.indexnow_key, "keyLocation": f"{site_url()}/{s.indexnow_key}.txt",
               "urlList": urls[:10000]}
    try:
        r = requests.post(INDEXNOW_ENDPOINT, json=payload, timeout=TIMEOUT,
                          headers={"Content-Type": "application/json; charset=utf-8"})
        ok = r.status_code in (200, 202)
        msg = INDEXNOW_CODES.get(r.status_code, f"HTTP {r.status_code}: {r.text[:300]}")
        return _record("indexnow", urls, ok, r.status_code, msg, user=user)
    except requests.RequestException as exc:
        return _record("indexnow", urls, False, None, f"Could not reach IndexNow: {exc.__class__.__name__}",
                       user=user)


# ---------------------------------------------------------------------------
# Google Indexing API (service account JWT, signed with `cryptography`)
# ---------------------------------------------------------------------------
def _b64(data):
    return base64.urlsafe_b64encode(data).rstrip(b"=")


def parse_service_account(raw):
    try:
        info = json.loads(raw or "")
    except ValueError:
        raise IndexingError("The service account key is not valid JSON.")
    for k in ("client_email", "private_key", "token_uri"):
        if not info.get(k):
            raise IndexingError(f"The service account key is missing '{k}'. Download a new JSON key.")
    if info.get("type") != "service_account":
        raise IndexingError("This JSON is not a service account key.")
    return info


def _google_token(info):
    key = f"google_indexing_token:{info['client_email']}"
    tok = cache.get(key)
    if tok:
        return tok
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding
    now = int(time.time())
    header = {"alg": "RS256", "typ": "JWT", "kid": info.get("private_key_id", "")}
    claims = {"iss": info["client_email"], "scope": GOOGLE_SCOPE, "aud": info.get("token_uri", GOOGLE_TOKEN_URL),
              "iat": now, "exp": now + 3600}
    signing_input = _b64(json.dumps(header).encode()) + b"." + _b64(json.dumps(claims).encode())
    try:
        pk = serialization.load_pem_private_key(info["private_key"].encode(), password=None)
    except ValueError:
        raise IndexingError("The private key inside the service account JSON can't be read.")
    signature = pk.sign(signing_input, padding.PKCS1v15(), hashes.SHA256())
    assertion = (signing_input + b"." + _b64(signature)).decode()
    try:
        r = requests.post(info.get("token_uri", GOOGLE_TOKEN_URL), timeout=TIMEOUT, data={
            "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer", "assertion": assertion})
    except requests.RequestException as exc:
        raise IndexingError(f"Could not reach Google: {exc.__class__.__name__}")
    if r.status_code != 200:
        raise IndexingError("Google refused the service account key "
                            f"({r.json().get('error_description', r.status_code) if r.content else r.status_code}).")
    tok = r.json()["access_token"]
    cache.set(key, tok, 3000)
    return tok


GOOGLE_HINTS = {
    403: "Permission denied: add the service account e-mail as an Owner of the property in Search Console, "
         "and enable the 'Web Search Indexing API' in Google Cloud.",
    429: "Daily quota reached (200 URLs/day by default).",
}


def google_submit(urls, action="URL_UPDATED", user=None, force=False):
    s = SeoSettings.get()
    if not (s.google_indexing_enabled or force) or s.hide_from_search_engines:
        return None
    urls = _own_urls(urls)
    if not urls:
        return None
    try:
        info = parse_service_account(s.google_service_account)
        token = _google_token(info)
    except IndexingError as exc:
        return _record("google", urls, False, None, str(exc), action=action.lower(), user=user)
    done, errors, last_code = 0, [], None
    for u in urls[:100]:
        try:
            r = requests.post(GOOGLE_PUBLISH_URL, timeout=TIMEOUT, json={"url": u, "type": action},
                              headers={"Authorization": f"Bearer {token}"})
        except requests.RequestException as exc:
            errors.append(f"{u}: {exc.__class__.__name__}")
            continue
        last_code = r.status_code
        if r.status_code == 200:
            done += 1
        else:
            hint = GOOGLE_HINTS.get(r.status_code)
            try:
                detail = r.json().get("error", {}).get("message", "")
            except ValueError:
                detail = ""
            errors.append(hint or f"{u}: HTTP {r.status_code} {detail}".strip())
            if r.status_code in (403, 429):
                break
    ok = done == len(urls[:100]) and not errors
    msg = f"{done} of {len(urls[:100])} URL(s) sent." + (" " + " | ".join(dict.fromkeys(errors)) if errors else "")
    return _record("google", urls[:100], ok, last_code, msg, action=action.lower(), user=user)


def test_google_credentials(raw):
    info = parse_service_account(raw)
    _google_token(info)
    return info["client_email"]


def notify(urls, deleted=False, user=None):
    """Tell every enabled engine that these URLs changed (or were removed)."""
    results = [indexnow_submit(urls, user=user),
               google_submit(urls, action="URL_DELETED" if deleted else "URL_UPDATED", user=user)]
    return [r for r in results if r is not None]
