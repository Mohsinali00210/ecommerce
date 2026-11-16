import logging

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_POST

from accounts import rbac
from accounts.error_logging import log_error, security_event
from accounts.models import ErrorLog, SecurityEvent

from . import dashboard as dash
from .session import session_state, touch

User = get_user_model()
log = logging.getLogger("app")

# Access to every view here is enforced by accounts.rbac.AdminAccessMiddleware
# (see ADMIN_RULES). The checks below are a second line of defence.


def _staff(request):
    return request.user.is_authenticated and request.user.is_staff


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------
def dashboard_page(request):
    if not rbac.has_admin_perm(request.user, "view_dashboard"):
        # Staff without dashboard access land on the first section they can use.
        perms = rbac.user_permissions(request.user)
        from django.urls import NoReverseMatch, reverse
        for perm, name in [("view_orders", "Orders"), ("view_catalog", "products"),
                           ("view_customers", "users-page")]:
            if perm in perms:
                try:
                    return redirect(reverse(name))
                except NoReverseMatch:
                    continue
        return render(request, "errors/403.html", {"message": "Your account has no admin role yet."},
                      status=403)
    first_name = (request.user.full_name or "").split(" ")[0]
    return render(request, "adminpanel/dashboard.html", {"first_name": first_name, "presets": [
        ("today", "Today"), ("7d", "7 days"), ("30d", "30 days"), ("month", "This month"),
        ("90d", "90 days"), ("365d", "12 months")]})


@require_GET
def dashboard_data(request):
    if not rbac.has_admin_perm(request.user, "view_dashboard"):
        return JsonResponse({"detail": "You don't have permission to do this."}, status=403)
    return JsonResponse(dash.build(request.GET))


# ---------------------------------------------------------------------------
# Session
# ---------------------------------------------------------------------------
@require_GET
def session_status(request):
    if not _staff(request):
        return JsonResponse({"detail": "Not signed in.", "code": "not_authenticated"}, status=401)
    return JsonResponse(session_state(request))


@require_POST
def session_extend(request):
    """'Stay signed in' button and the activity ping."""
    if not _staff(request):
        return JsonResponse({"detail": "Not signed in.", "code": "not_authenticated"}, status=401)
    touch(request)
    if request.POST.get("manual") == "1":
        security_event("session_extended", request)
    return JsonResponse(session_state(request))


@require_GET
def session_token(request):
    if not _staff(request):
        return JsonResponse({"detail": "Not signed in.", "code": "not_authenticated"}, status=401)
    from .context_processors import _admin_jwt
    return JsonResponse({"access": _admin_jwt(request.user)()})


# ---------------------------------------------------------------------------
# Logs (view_logs)
# ---------------------------------------------------------------------------
def logs_page(request):
    tab = request.GET.get("tab", "errors")
    q = request.GET.get("q", "").strip()
    severity = request.GET.get("severity", "")
    if tab == "security":
        qs = SecurityEvent.objects.select_related("user")
        if q:
            qs = qs.filter(Q(event__icontains=q) | Q(username__icontains=q) | Q(ip_address__icontains=q)
                           | Q(path__icontains=q) | Q(request_id__iexact=q))
        if request.GET.get("event"):
            qs = qs.filter(event=request.GET["event"])
        events = SecurityEvent.objects.values_list("event", flat=True).distinct().order_by("event")
    else:
        tab = "errors"
        qs = ErrorLog.objects.select_related("user").order_by("-created_at")
        if q:
            qs = qs.filter(Q(error_message__icontains=q) | Q(endpoint__icontains=q) | Q(request_id__iexact=q))
        if request.GET.get("status"):
            qs = qs.filter(status_code=request.GET["status"]) if request.GET["status"].isdigit() else qs
        events = []
    if severity:
        qs = qs.filter(severity=severity)
    page = Paginator(qs, 30).get_page(request.GET.get("page"))
    return render(request, "adminpanel/logs.html", {"tab": tab, "page": page, "q": q, "severity": severity,
                                                     "events": events, "f_event": request.GET.get("event", ""),
                                                     "f_status": request.GET.get("status", "")})


def log_detail(request, kind, pk):
    obj = get_object_or_404(SecurityEvent if kind == "security" else ErrorLog, pk=pk)
    return render(request, "adminpanel/log_detail.html", {"obj": obj, "kind": kind})


# ---------------------------------------------------------------------------
# Team & roles (manage_roles = superusers by default)
# ---------------------------------------------------------------------------
def team_page(request):
    roles = list(Group.objects.filter(name__in=rbac.ROLES.keys()).order_by("name"))
    staff = User.objects.filter(is_staff=True).prefetch_related("groups").order_by("-is_superuser", "email")
    return render(request, "adminpanel/team.html", {
        "staff": staff, "roles": roles,
        "role_perms": {name: [p.replace("_", " ") for p in perms] for name, perms in rbac.ROLES.items()},
    })


@require_POST
def team_update(request, user_id):
    member = get_object_or_404(User, pk=user_id)
    if member.is_superuser:
        return JsonResponse({"detail": "Super admins always have full access."}, status=400)
    if member.pk == request.user.pk:
        return JsonResponse({"detail": "You can't change your own roles."}, status=400)
    wanted = set(request.POST.getlist("roles"))
    valid = Group.objects.filter(name__in=rbac.ROLES.keys())
    if wanted - set(valid.values_list("name", flat=True)):
        return JsonResponse({"detail": "Unknown role."}, status=400)
    before = sorted(member.groups.filter(name__in=rbac.ROLES.keys()).values_list("name", flat=True))
    member.groups.remove(*valid)
    member.groups.add(*valid.filter(name__in=wanted))
    is_staff = request.POST.get("is_staff", "1") == "1"
    if member.is_staff != is_staff:
        member.is_staff = is_staff
        member.save(update_fields=["is_staff"])
    security_event("roles_changed", request, severity="WARNING", target=member.email,
                   before=before, after=sorted(wanted), staff=is_staff)
    return JsonResponse({"ok": True, "roles": sorted(wanted), "is_staff": is_staff})


@require_POST
def team_add(request):
    email = (request.POST.get("email") or "").strip().lower()
    member = User.objects.filter(email__iexact=email).first()
    if not member:
        return JsonResponse({"detail": "No account with that email. Ask them to register first."}, status=404)
    if member.is_staff:
        return JsonResponse({"detail": "This person is already on the team."}, status=400)
    member.is_staff = True
    member.save(update_fields=["is_staff"])
    role = request.POST.get("role")
    if role in rbac.ROLES:
        member.groups.add(Group.objects.get(name=role))
    security_event("staff_added", request, severity="WARNING", target=member.email, role=role or "")
    return JsonResponse({"ok": True})


# ---------------------------------------------------------------------------
# Friendly error pages (never show technical details)
# ---------------------------------------------------------------------------
def _error_response(request, status, title, message, template=None):
    wants_json = ("/api/" in request.path or request.headers.get("x-requested-with") == "XMLHttpRequest"
                  or "application/json" in request.headers.get("accept", ""))
    ref = getattr(request, "request_id", "")
    if wants_json:
        return JsonResponse({"detail": message, "reference": ref}, status=status)
    # Rendered without context processors: an error page must not depend on
    # the code that may have just failed.
    from django.http import HttpResponse
    from django.template.loader import render_to_string
    html = render_to_string(template or "errors/error.html",
                            {"status": status, "title": title, "message": message, "reference": ref,
                             "is_admin": request.path.startswith("/Adminpanel/")})
    return HttpResponse(html, status=status)


def error_400(request, exception=None):
    return _error_response(request, 400, "Bad request", "We couldn't understand that request.")


def error_403(request, exception=None):
    from django_ratelimit.exceptions import Ratelimited
    if isinstance(exception, Ratelimited):
        security_event("rate_limited", request, severity="WARNING")
        return _error_response(request, 429, "Too many attempts",
                               "Too many attempts. Please wait a few minutes and try again.")
    return _error_response(request, 403, "Access denied", "You don't have permission to view this page.")


def error_404(request, exception=None):
    return _error_response(request, 404, "Page not found", "The page you're looking for doesn't exist or was moved.")


def error_500(request):
    return _error_response(request, 500, "Something went wrong",
                           "An unexpected error occurred. Our team has been notified - please try again.")


def csrf_failure(request, reason=""):
    security_event("csrf_failure", request, severity="WARNING", reason=reason[:200])
    return _error_response(request, 403, "Page expired",
                           "This form expired or was opened in another session. Reload the page and try again.")
