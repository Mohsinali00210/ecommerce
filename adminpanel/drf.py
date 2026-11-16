"""DRF exception handler: clean JSON errors, never a stack trace."""
from rest_framework.views import exception_handler as drf_default


def exception_handler(exc, context):
    response = drf_default(exc, context)
    request = context.get("request")
    if response is not None:
        if response.status_code in (401, 403) and request is not None:
            from accounts.error_logging import security_event
            if response.status_code == 403:
                security_event("api_forbidden", request, severity="WARNING",
                               view=type(context.get("view")).__name__)
        return response
    # Unhandled error: log everything, show nothing technical.
    from django.http import JsonResponse
    from accounts.error_logging import log_error
    django_request = getattr(request, "_request", request)
    log_error(django_request, exc, 500)
    return JsonResponse({"detail": "Something went wrong. Please try again.",
                         "reference": getattr(django_request, "request_id", "")}, status=500)
