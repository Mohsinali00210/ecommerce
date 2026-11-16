from datetime import timedelta

from django.conf import settings


def _admin_jwt(user):
    """Short-lived access token for the admin panel's API calls. Rendered into
    the page (sessionStorage only) so there's no race with the first API call,
    and no long-lived refresh token is stored in the browser."""
    def make():
        from rest_framework_simplejwt.tokens import AccessToken
        token = AccessToken.for_user(user)
        token.set_exp(lifetime=timedelta(minutes=getattr(settings, "ADMIN_JWT_MINUTES", 15)))
        return str(token)
    return make


def admin_ui(request):
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated or not user.is_staff:
        return {}
    from accounts import rbac
    from .session import session_state
    perms = rbac.user_permissions(user)
    from .unseen import counts
    return {
        "admin_unseen": counts(user),
        "admin_perms": perms,
        "admin_roles": rbac.role_names(user),
        "admin_session": session_state(request),
        "admin_jwt": _admin_jwt(user),
        "admin_jwt_minutes": getattr(settings, "ADMIN_JWT_MINUTES", 15),
    }
