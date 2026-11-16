"""
Role-based access control for the admin panel.

* Roles are Django groups (created/updated automatically after `migrate`).
* Each admin URL maps to one permission for reading (GET) and one for changes
  (POST/PUT/PATCH/DELETE) in ADMIN_RULES below - the single place to look.
* Superusers can do everything. Staff users get what their roles allow.
* AdminAccessMiddleware enforces it for every admin page *and* admin API, so a
  view can't be forgotten. The DRF permission classes ask the same function.

Assign roles in Admin panel > Team & roles (or Django admin > Groups).
"""
import re

from django.contrib.auth.models import Group, Permission
from django.http import JsonResponse
from django.shortcuts import redirect
from django.urls import reverse

P = "accounts."  # permission app label prefix

# Role name -> permissions (codename without the app label)
ROLES = {
    "Administrator": ["view_dashboard", "view_catalog", "manage_catalog", "view_orders", "manage_orders",
                      "manage_shipping", "view_customers", "manage_customers", "manage_support",
                      "manage_marketing", "manage_finance", "view_logs", "manage_settings"],
    "Store Manager": ["view_dashboard", "view_catalog", "manage_catalog", "view_orders", "manage_orders",
                      "manage_shipping", "view_customers", "manage_support", "manage_marketing"],
    "Catalog Manager": ["view_dashboard", "view_catalog", "manage_catalog", "manage_marketing"],
    "Order Manager": ["view_dashboard", "view_catalog", "view_orders", "manage_orders", "manage_shipping",
                      "view_customers"],
    "Support Agent": ["view_catalog", "view_orders", "view_customers", "manage_support"],
    "Analyst": ["view_dashboard", "view_catalog", "view_orders", "view_customers"],
}

# (path regex, permission for safe methods, permission for unsafe methods)
# First match wins. None = any staff user.
ADMIN_RULES = [
    # dashboard, session, logs, roles
    # the dashboard page itself sends staff without dashboard access to a page they can use
    (r"^/Adminpanel/(Dashboard/)?$", None, None),
    (r"^/Adminpanel/Dashboard/", "view_dashboard", "view_dashboard"),
    (r"^/Adminpanel/Session/", None, None),
    (r"^/Adminpanel/Logs/", "view_logs", "view_logs"),
    (r"^/Adminpanel/Team/", "manage_roles", "manage_roles"),
    (r"^/Adminpanel/Reports/", "view_dashboard", "view_dashboard"),
    (r"^/Adminpanel/Settings/", "manage_settings", "manage_settings"),
    (r"^/Adminpanel/Backups/", "manage_backups", "manage_backups"),
    (r"^/Adminpanel/Requests/", "view_orders", "manage_orders"),
    (r"^/Adminpanel/Payments/gateway/", "manage_finance", "manage_finance"),
    (r"^/Adminpanel/Payments/", "view_orders", "manage_finance"),
    # shipping
    (r"^/Adminpanel/Couriers/settings/", "manage_shipping", "manage_shipping"),
    (r"^/Adminpanel/Couriers/", "view_orders", "manage_shipping"),
    # orders
    (r"^/Adminpanel/Products/(Orders|OrdersByStatus|GetOrders|orderdetail|orderupdate|"
     r"AdminOrderRequestUpdate)/", "view_orders", "manage_orders"),
    (r"^/Adminpanel/Products/api/v1/(orders|order-requests|orderrequests)", "view_orders", "manage_orders"),
    # support
    (r"^/Adminpanel/Products/(support-tickets|reviews|reviews-page)/", "manage_support", "manage_support"),
    (r"^/chat/(admin|admin-tickets|questions)", "manage_support", "manage_support"),
    # marketing
    (r"^/Adminpanel/Products/(promotions-page|admin/promotions|Blog-post|topbar|picture-page)",
     "view_catalog", "manage_marketing"),
    (r"^/Adminpanel/Products/api/v1/(promotions|promotionss|pictures|posts|postscat)/", "view_catalog",
     "manage_marketing"),
    # finance
    (r"^/Adminpanel/Products/manage/withdrawals", "manage_finance", "manage_finance"),
    # customers
    (r"^/Adminpanel/Products/(wishlist|admin/wish-to-buy|api/wish-to-buy)", "view_customers", "view_customers"),
    (r"^/api/v1/(users|users-page|admin/users)", "view_customers", "manage_customers"),
    # everything else in the catalog (products, categories, brands, attributes, inventory...)
    (r"^/Adminpanel/Products/", "view_catalog", "manage_catalog"),
    # any other admin page: staff only
    (r"^/Adminpanel/", None, None),
]
_COMPILED = [(re.compile(rx), v, m) for rx, v, m in ADMIN_RULES]
ADMIN_PREFIXES = ("/Adminpanel/", "/chat/admin", "/chat/questions", "/api/v1/users",
                  "/api/v1/admin/users", "/api/v1/users-page")
SAFE_METHODS = ("GET", "HEAD", "OPTIONS")


def is_admin_path(path):
    return path.startswith(ADMIN_PREFIXES)


def required_permission(path, method):
    for rx, view_perm, manage_perm in _COMPILED:
        if rx.match(path):
            return view_perm if method in SAFE_METHODS else manage_perm
    return None


def has_admin_perm(user, codename):
    if not getattr(user, "is_authenticated", False) or not user.is_active or not user.is_staff:
        return False
    if user.is_superuser or codename is None:
        return True
    return user.has_perm(P + codename)


def allowed(user, path, method):
    return has_admin_perm(user, required_permission(path, method))


def user_permissions(user):
    """Set of admin permission codenames - used by templates to show/hide menus."""
    if not getattr(user, "is_authenticated", False) or not user.is_staff:
        return set()
    every = {c for perms in ROLES.values() for c in perms} | {"manage_roles", "view_logs", "manage_backups"}
    if user.is_superuser:
        return every
    return {c for c in every if user.has_perm(P + c)}


def role_names(user):
    if getattr(user, "is_superuser", False):
        return ["Super Admin"]
    return list(user.groups.filter(name__in=ROLES.keys()).values_list("name", flat=True))


def sync_roles(**kwargs):
    """Create/refresh the role groups. Runs after every migrate (idempotent)."""
    perms = {p.codename: p for p in Permission.objects.filter(content_type__app_label="accounts",
                                                               content_type__model="adminaccess")}
    if not perms:
        return
    for name, codes in ROLES.items():
        group, _ = Group.objects.get_or_create(name=name)
        group.permissions.add(*[perms[c] for c in codes if c in perms])


def _wants_json(request):
    return (request.path.startswith(("/api/", "/Adminpanel/Products/api/"))
            or "/api/" in request.path
            or request.headers.get("x-requested-with") == "XMLHttpRequest"
            or "application/json" in request.headers.get("accept", "")
            or request.headers.get("authorization", "").startswith("Bearer "))


def _jwt_user(request):
    try:
        from rest_framework_simplejwt.authentication import JWTAuthentication
        res = JWTAuthentication().authenticate(request)
        return res[0] if res else None
    except Exception:
        return None


class AdminAccessMiddleware:
    """Enforces ADMIN_RULES for every admin URL (pages and APIs)."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path
        if not is_admin_path(path):
            return self.get_response(request)

        user = request.user
        if not user.is_authenticated and request.headers.get("authorization", "").startswith("Bearer "):
            # API client without a browser session
            user = _jwt_user(request) or user

        if not user.is_authenticated:
            if _wants_json(request):
                return JsonResponse({"detail": "Your session has expired. Please sign in again.",
                                     "code": "not_authenticated"}, status=401)
            return redirect(f"{reverse('login')}?next={request.get_full_path()}")

        perm = required_permission(path, request.method)
        if has_admin_perm(user, perm):
            return self.get_response(request)

        from accounts.error_logging import security_event
        security_event("access_denied", request, user=user, severity="WARNING",
                       required=perm or "staff", method=request.method)
        if _wants_json(request):
            return JsonResponse({"detail": "You don't have permission to do this.",
                                 "code": "permission_denied"}, status=403)
        from django.shortcuts import render
        return render(request, "errors/403.html",
                      {"message": "Your role doesn't include access to this page. "
                                  "Ask an administrator if you need it."}, status=403)
