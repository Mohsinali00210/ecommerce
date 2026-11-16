"""
One-time email codes protecting dangerous admin actions (backup download / restore).

* 6-digit code from `secrets`, stored only as a hash, valid 10 minutes, 5 attempts.
* A correct code grants that action for 10 minutes in this browser session only.
* Restore grants are single-use.
"""
import hashlib
import hmac
import secrets
import time

from django.conf import settings
from django.core.cache import cache

TTL = 10 * 60
GRANT_TTL = 10 * 60
MAX_ATTEMPTS = 5
PURPOSES = {"download": "download a backup", "restore": "restore a backup"}


def _key(user, purpose):
    return f"admin-otp:{purpose}:{user.pk}"


def _hash(code):
    return hmac.new(settings.SECRET_KEY.encode(), code.encode(), hashlib.sha256).hexdigest()


def issue(request, purpose):
    from accounts.error_logging import security_event
    from accounts.utils import send_templated_email
    user = request.user
    code = f"{secrets.randbelow(1_000_000):06d}"
    cache.set(_key(user, purpose), {"h": _hash(code), "tries": 0}, TTL)
    send_templated_email(
        to_email=user.email,
        subject=f"Your Shan Zee admin code: {code}",
        template_name="adminpanel/emails/otp.html",
        context={"code": code, "action": PURPOSES[purpose], "user": user,
                 "ip": request.META.get("REMOTE_ADDR"), "minutes": TTL // 60},
    )
    security_event("otp_sent", request, purpose=purpose)


def verify(request, purpose, code):
    from accounts.error_logging import security_event
    key = _key(request.user, purpose)
    data = cache.get(key)
    if not data:
        return False, "The code expired. Request a new one."
    if data["tries"] >= MAX_ATTEMPTS:
        cache.delete(key)
        security_event("otp_locked", request, severity="WARNING", purpose=purpose)
        return False, "Too many wrong codes. Request a new one."
    if not hmac.compare_digest(data["h"], _hash((code or "").strip())):
        data["tries"] += 1
        cache.set(key, data, TTL)
        security_event("otp_failed", request, severity="WARNING", purpose=purpose)
        return False, f"Wrong code. {MAX_ATTEMPTS - data['tries']} attempt(s) left."
    cache.delete(key)
    request.session[f"otp_ok:{purpose}"] = int(time.time()) + GRANT_TTL
    security_event("otp_verified", request, purpose=purpose)
    return True, "Verified."


def granted(request, purpose, consume=False):
    until = request.session.get(f"otp_ok:{purpose}", 0)
    ok = until > time.time()
    if consume and ok:
        request.session.pop(f"otp_ok:{purpose}", None)
    return ok


def seconds_left(request, purpose):
    return max(0, int(request.session.get(f"otp_ok:{purpose}", 0) - time.time()))
