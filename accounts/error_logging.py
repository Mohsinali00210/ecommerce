import json
import logging
import traceback

from django.core.exceptions import PermissionDenied
from django.http import Http404

logger = logging.getLogger(__name__)

SENSITIVE_KEYS = ("password", "token", "secret", "card", "cvv", "otp",
                  "authorization", "csrf", "api_key")
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
        if request.content_type == "application/json":
            return _clean(json.loads(request.body or b"{}"))
        data = _querydict(request.POST)
        if request.FILES:
            data["_files"] = list(request.FILES.keys())
        return _clean(data) or None
    except Exception:
        return None


def log_error(request, exc=None, status_code=500, message=None):
    """Never raises. Logs at most once per request."""
    if getattr(request, "_error_logged", False):
        return
    request._error_logged = True
    try:
        from accounts.models import ErrorLog

        user = getattr(request, "user", None)
        ErrorLog.objects.create(
            user=user if getattr(user, "is_authenticated", False) else None,
            endpoint=request.path[:255],
            method=request.method[:10],
            error_message=message or (f"{type(exc).__name__}: {exc}" if exc else "Unknown error"),
            stack_trace="".join(
                traceback.format_exception(type(exc), exc, exc.__traceback__)
            ) if exc else None,
            status_code=status_code,
            request_data=_request_data(request),
            query_params=_clean(_querydict(request.GET)) or None,
        )
    except Exception:
        logger.exception("Failed to write ErrorLog")


class ErrorLogMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        # Catches 500 responses the view returned itself (no exception reached us)
        if response.status_code >= 500:
            log_error(request, status_code=response.status_code,
                      message=f"Server error response ({response.status_code})")
        return response

    def process_exception(self, request, exception):
        if isinstance(exception, (Http404, PermissionDenied)):
            return None
        log_error(request, exception, 500)
        return None  # let Django render the normal 500 page