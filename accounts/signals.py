"""Security audit hooks for authentication events."""
from django.contrib.auth.signals import user_logged_in, user_logged_out, user_login_failed
from django.dispatch import receiver
from django.utils import timezone

from .error_logging import security_event


@receiver(user_logged_in)
def _on_login(sender, request, user, **kwargs):
    if request is not None and hasattr(request, "session"):
        # Start the admin session clock (see accounts/session.py)
        now = int(timezone.now().timestamp())
        request.session["_auth_at"] = now
        request.session["_last_activity"] = now
        if user.is_staff:
            # Staff: the session cookie dies when the browser closes.
            request.session.set_expiry(0)
    security_event("login", request, user=user, staff=bool(user.is_staff))


@receiver(user_logged_out)
def _on_logout(sender, request, user, **kwargs):
    reason = getattr(request, "_logout_reason", "user") if request is not None else "user"
    security_event("logout", request, user=user, reason=reason)


@receiver(user_login_failed)
def _on_login_failed(sender, credentials, request=None, **kwargs):
    username = (credentials or {}).get("username") or (credentials or {}).get("email") or ""
    security_event("login_failed", request, severity="WARNING", username=str(username)[:254])
