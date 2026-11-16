"""
"New since you last looked" badges for every admin section.

Each section: which records count, which URL(s) mark it as seen, and the
permission needed. Visiting a section page (a real page navigation) marks it
seen for that staff member. Counts are cached per user for 30 seconds.
"""
import re
from datetime import timedelta

from django.core.cache import cache
from django.db.models import Q
from django.utils import timezone

from accounts import rbac

CACHE_TTL = 30
FIRST_VISIT_LOOKBACK = timedelta(days=7)


def _orderrequests(since):
    from Web.models import OrderRequest
    return OrderRequest.objects.filter(created_at__gt=since, is_deleted=False)


def _tickets(since):
    from Web.models import SupportTicket, SupportTicketReply
    return (SupportTicket.objects.filter(created_at__gt=since).count()
            + SupportTicketReply.objects.filter(created_at__gt=since, is_staff_reply=False).count())


def _messages(since):
    from Web.models import ChatMessage
    return ChatMessage.objects.filter(created_at__gt=since).exclude(sender_type="admin")


def _questions(since):
    from products.models import ProductQuestion
    return ProductQuestion.objects.filter(created_at__gt=since, is_deleted=False)


def _reviews(since):
    from products.models import ProductReview
    return ProductReview.objects.filter(created_at__gt=since, is_deleted=False)


def _withdrawals(since):
    from Web.models import WithdrawalRequest
    return WithdrawalRequest.objects.filter(created_at__gt=since)


def _wish(since):
    from Web.models import WishToBuy
    return WishToBuy.objects.filter(created_at__gt=since, is_deleted=False)


def _customers(since):
    from accounts.models import User
    return User.objects.filter(date_joined__gt=since, is_staff=False)


def _payments(since):
    from payments.models import Payment
    return Payment.objects.filter(Q(proof_uploaded_at__gt=since) | Q(created_at__gt=since, method="online",
                                                                       status="paid"))


def _shipments_attention(_since):
    from couriers.models import Shipment
    return Shipment.objects.filter(Q(status__in=["booking_failed", "delivery_failed"]) | Q(unmapped_status=True)
                                   | Q(tracking_failures__gte=3)).count()


def _requests_pending(_since):
    from Web.models import OrderRequest
    return OrderRequest.objects.filter(status="pending", is_deleted=False).count()


def _receipts_pending(_since):
    from payments.models import Payment
    return Payment.objects.filter(method="bank", status="pending", proof_uploaded_at__isnull=False).count()


# key: (counter, permission, [url regexes that mark it seen], label)
SECTIONS = {
    "order_requests": (_orderrequests, "view_orders", [r"^/Adminpanel/Requests/"], "Return / cancel requests"),
    "tickets": (_tickets, "manage_support", [r"^/chat/admin-tickets/"], "Support tickets"),
    "messages": (_messages, "manage_support", [r"^/chat/admin/messages/"], "Product messages"),
    "questions": (_questions, "manage_support", [r"^/chat/questions/"], "Product questions"),
    "reviews": (_reviews, "manage_support", [r"^/Adminpanel/Products/reviews-page/"], "Reviews"),
    "withdrawals": (_withdrawals, "manage_finance", [r"^/Adminpanel/Products/manage/withdrawals/"], "Withdrawals"),
    "wish_to_buy": (_wish, "view_customers", [r"^/Adminpanel/Products/admin/wish-to-buy/"], "Wish to buy"),
    "customers": (_customers, "view_customers", [r"^/api/v1/admin/users/", r"^/api/v1/users-page/"], "Customers"),
    "payments": (_payments, "view_orders", [r"^/Adminpanel/Payments/$"], "Payments"),
}
# Things that need action regardless of when you looked (not cleared by visiting)
PENDING = {
    "shipments_attention": (_shipments_attention, "view_orders"),
    "requests_pending": (_requests_pending, "view_orders"),
    "receipts_pending": (_receipts_pending, "view_orders"),
}
_MATCHERS = [(key, re.compile(rx)) for key, (_, _, rxs, _) in SECTIONS.items() for rx in rxs]


def _cache_key(user):
    return f"admin-unseen:{user.pk}"


def counts(user):
    if not getattr(user, "is_authenticated", False) or not user.is_staff:
        return {}
    cached = cache.get(_cache_key(user))
    if cached is not None:
        return cached
    from .models import AdminSeen
    seen = dict(AdminSeen.objects.filter(user=user).values_list("section", "seen_at"))
    default = timezone.now() - FIRST_VISIT_LOOKBACK
    out = {}
    for key, (counter, perm, _, _) in SECTIONS.items():
        if rbac.has_admin_perm(user, perm):
            try:
                res = counter(seen.get(key, default))
                out[key] = res if isinstance(res, int) else res.count()
            except Exception:
                out[key] = 0
    for key, (counter, perm) in PENDING.items():
        if rbac.has_admin_perm(user, perm):
            try:
                out[key] = counter(None)
            except Exception:
                out[key] = 0
    # sidebar group totals
    out["support_total"] = sum(out.get(k, 0) for k in ("tickets", "messages", "questions", "reviews"))
    out["marketing_total"] = out.get("wish_to_buy", 0)
    out["shipping_total"] = out.get("shipments_attention", 0)
    cache.set(_cache_key(user), out, CACHE_TTL)
    return out


def mark_seen(user, path):
    from .models import AdminSeen
    keys = {key for key, rx in _MATCHERS if rx.match(path)}
    if not keys:
        return
    now = timezone.now()
    for key in keys:
        AdminSeen.objects.update_or_create(user=user, section=key, defaults={"seen_at": now})
    cache.delete(_cache_key(user))


class UnseenMiddleware:
    """Marks a section as seen when a staff member opens its page."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        user = getattr(request, "user", None)
        if (user is not None and user.is_authenticated and user.is_staff and request.method == "GET"
                and response.status_code == 200
                and request.META.get("HTTP_SEC_FETCH_MODE", "navigate") == "navigate"):
            try:
                mark_seen(user, request.path)
            except Exception:
                pass
        return response
