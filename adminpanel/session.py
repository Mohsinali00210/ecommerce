"""
Admin session lifetime.

* Idle timeout: a staff session ends after ADMIN_SESSION_IDLE_MINUTES without
  activity (page loads, form posts, API changes, or the panel's activity ping
  when the user moves the mouse / types).
* Absolute limit: it also ends ADMIN_SESSION_MAX_HOURS after sign-in, active or not.
* Browser close: staff session cookies have no expiry date, so closing the
  browser ends the session (set on login).
Background polling (GET fetches) does NOT count as activity, so an open but
unattended tab still times out.
"""
from django.conf import settings
from django.contrib.auth import logout
from django.http import JsonResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone

STATUS_PATH = "/Adminpanel/Session/status/"
TOKEN_PATH = "/Adminpanel/Session/token/"


def idle_seconds():
    return int(getattr(settings, "ADMIN_SESSION_IDLE_MINUTES", 60)) * 60


def max_seconds():
    return int(getattr(settings, "ADMIN_SESSION_MAX_HOURS", 12)) * 3600


def warning_seconds():
    return int(getattr(settings, "ADMIN_SESSION_WARNING_SECONDS", 120))


def _now():
    return int(timezone.now().timestamp())


def session_state(request):
    """Seconds left before the staff session ends (idle or absolute, whichever is first)."""
    s = request.session
    now = _now()
    last = int(s.get("_last_activity") or now)
    auth_at = int(s.get("_auth_at") or now)
    idle_left = last + idle_seconds() - now
    abs_left = auth_at + max_seconds() - now
    left = min(idle_left, abs_left)
    return {
        "remaining": max(left, 0),
        "idle_remaining": max(idle_left, 0),
        "absolute_remaining": max(abs_left, 0),
        "idle_timeout": idle_seconds(),
        "warning": warning_seconds(),
        "reason": "absolute" if abs_left <= idle_left else "idle",
    }


def touch(request):
    request.session["_last_activity"] = _now()


def _is_activity(request):
    if request.path in (STATUS_PATH, TOKEN_PATH):
        return False
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        return True
    mode = request.META.get("HTTP_SEC_FETCH_MODE")
    if mode is None:
        # Old browsers don't send Sec-Fetch-*; only XHR is treated as background.
        return request.headers.get("x-requested-with") != "XMLHttpRequest"
    return mode == "navigate"


class AdminSessionMiddleware:
    """Must sit after AuthenticationMiddleware and before AdminAccessMiddleware."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated and user.is_staff:
            s = request.session
            if "_auth_at" not in s:  # sessions that existed before this feature
                s["_auth_at"] = _now()
                s["_last_activity"] = _now()
            state = session_state(request)
            if state["remaining"] <= 0:
                return self._expire(request, state["reason"])
            if _is_activity(request):
                touch(request)
        return self.get_response(request)

    def _expire(self, request, reason):
        from accounts.error_logging import security_event
        security_event("session_timeout", request, user=request.user, reason=reason)
        request._logout_reason = f"timeout:{reason}"
        logout(request)
        wants_json = (request.path.startswith("/Adminpanel/Session/") or "/api/" in request.path
                      or request.headers.get("x-requested-with") == "XMLHttpRequest"
                      or "application/json" in request.headers.get("accept", "")
                      or request.META.get("HTTP_SEC_FETCH_MODE") in ("cors", "same-origin"))
        if wants_json:
            return JsonResponse({"detail": "Your session has expired. Please sign in again.",
                                 "code": "session_expired"}, status=401)
        return redirect(f"{reverse('login')}?expired=1&next={request.get_full_path()}")
