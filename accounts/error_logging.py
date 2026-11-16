"""
Centralised logging.

* Application / error log  -> logger "app"      -> logs/app.log, logs/error.log + ErrorLog table
* Security / audit log     -> logger "security" -> logs/security.log          + SecurityEvent table

Every entry carries a timestamp, severity, request id, user, IP, path, method and
(for errors) the exception and stack trace. Request data is sanitised: secrets are
masked, files are listed by name only, long values are truncated.
Nothing in here ever raises - logging must not break a request.
"""
import json
import logging
import traceback
import uuid

from django.core.exceptions import PermissionDenied
from django.http import Http404

app_logger = logging.getLogger("app")
security_logger = logging.getLogger("security")
logger = app_logger  # backwards compatibility

SENSITIVE_KEYS = ("password", "token", "secret", "card", "cvv", "otp",
                  "authorization", "csrf", "api_key", "session", "cookie")
MAX_LEN = 2000


def _clean(value, key=""):
    """Mask sensitive fields, truncate long values, keep everything JSON-safe."""
    if any(s in key.lower() for s in SENSITIVE_KEYS):
        return "***"
    if isinstance(value, dict):
        return {str(k): _clean(v, str(k)) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_clean(v, key) for v in value][:50]
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return str(value)[:MAX_LEN]


def _querydict(qd):
    return {k: (v[0] if len(v) == 1 else v) for k, v in qd.lists()}


def _request_data(request):
    try:
        if request.method in ("GET", "HEAD", "OPTIONS"):
            return None
        if request.content_type == "application/json":
            return _clean(json.loads(request.body or b"{}"))
        data = _querydict(request.POST)
        if request.FILES:
            data["_files"] = [f"{k}: {f.name} ({f.size} bytes)" for k, f in request.FILES.items()]
        return _clean(data) or None
    except Exception:
        return None


def client_ip(request):
    from django.conf import settings
    key = getattr(settings, "RATELIMIT_IP_META_KEY", "REMOTE_ADDR")
    if not isinstance(key, str):
        key = "REMOTE_ADDR"
    ip = request.META.get(key) or request.META.get("REMOTE_ADDR") or ""
    return ip.split(",")[0].strip()[:45] or None


def request_context(request):
    if request is None:
        return {}
    user = getattr(request, "user", None)
    return {
        "request_id": getattr(request, "request_id", None),
        "user_id": getattr(user, "pk", None) if getattr(user, "is_authenticated", False) else None,
        "user": getattr(user, "email", None) if getattr(user, "is_authenticated", False) else None,
        "ip": client_ip(request),
        "method": request.method,
        "path": request.path[:255],
        "user_agent": request.META.get("HTTP_USER_AGENT", "")[:255],
    }


def log_error(request, exc=None, status_code=500, message=None, severity="ERROR", once=True):
    """Record an application error. Never raises.

    `once=True` keeps one entry per request (the middleware and a view may both
    see the same exception)."""
    if request is not None and once:
        if getattr(request, "_error_logged", False):
            return
        request._error_logged = True
    severity = severity.upper()
    msg = message or (f"{type(exc).__name__}: {exc}" if exc else "Unknown error")
    stack = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__)) if exc else None
    ctx = request_context(request)
    try:
        app_logger.log(getattr(logging, severity, logging.ERROR), msg,
                       exc_info=(type(exc), exc, exc.__traceback__) if exc else None,
                       extra={"ctx": {**ctx, "status": status_code}})
    except Exception:
        pass
    try:
        from accounts.models import ErrorLog
        user = getattr(request, "user", None) if request is not None else None
        ErrorLog.objects.create(
            user=user if getattr(user, "is_authenticated", False) else None,
            endpoint=(ctx.get("path") or "")[:255],
            method=(ctx.get("method") or "")[:10],
            error_message=msg[:10000],
            stack_trace=stack,
            status_code=status_code,
            severity=severity,
            request_id=ctx.get("request_id") or "",
            ip_address=ctx.get("ip"),
            user_agent=ctx.get("user_agent") or "",
            request_data=_request_data(request) if request is not None else None,
            query_params=(_clean(_querydict(request.GET)) or None) if request is not None else None,
        )
    except Exception:
        app_logger.exception("Failed to write ErrorLog")


def security_event(event, request=None, user=None, severity="INFO", username="", **details):
    """Record a security/audit event (login, logout, denied access, admin changes...)."""
    severity = severity.upper()
    ctx = request_context(request)
    if user is None and request is not None and getattr(getattr(request, "user", None), "is_authenticated", False):
        user = request.user
    try:
        security_logger.log(getattr(logging, severity, logging.INFO), event,
                            extra={"ctx": {**ctx, "event": event, "username": username,
                                           "user_id": getattr(user, "pk", ctx.get("user_id")),
                                           "details": _clean(details)}})
    except Exception:
        pass
    try:
        from accounts.models import SecurityEvent
        SecurityEvent.objects.create(
            event=event[:50], severity=severity,
            user=user if getattr(user, "pk", None) else None,
            username=(username or getattr(user, "email", "") or "")[:254],
            ip_address=ctx.get("ip"), user_agent=ctx.get("user_agent") or "",
            path=ctx.get("path") or "", method=ctx.get("method") or "",
            request_id=ctx.get("request_id") or "", details=_clean(details) or {},
        )
    except Exception:
        security_logger.exception("Failed to write SecurityEvent")


class RequestIDMiddleware:
    """Gives every request a short id: in logs, error pages and the X-Request-ID header."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        incoming = request.META.get("HTTP_X_REQUEST_ID", "")
        request.request_id = incoming[:32] if incoming.isalnum() else uuid.uuid4().hex[:12]
        response = self.get_response(request)
        response["X-Request-ID"] = request.request_id
        return response


class ErrorLogMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        # Catches 500 responses the view returned itself (no exception reached us)
        if response.status_code >= 500:
            log_error(request, status_code=response.status_code,
                      message=f"Server error response ({response.status_code})")
        elif response.status_code == 403 and getattr(request, "user", None) is not None \
                and request.path.startswith(("/Adminpanel/", "/admin/", "/api/v1/users")):
            security_event("access_denied", request, severity="WARNING", status=403)
        return response

    def process_exception(self, request, exception):
        if isinstance(exception, (Http404, PermissionDenied)):
            return None
        log_error(request, exception, 500)
        return None  # Django renders the friendly 500 page (handler500)
