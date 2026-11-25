"""One transaction history from three sources: order payments, wallet movements, withdrawals.
Used by Admin > Payments > Transactions and the customer's Account > Transactions page."""
from decimal import Decimal

from django.db.models import Q

KINDS = [("", "All"), ("payment", "Order payments"), ("wallet", "Wallet"), ("withdrawal", "Withdrawals")]
LIMIT = 500  # rows read per source for the merged "All" view


def _payments(user=None, q="", status=""):
    from .models import Payment
    qs = Payment.objects.select_related("order", "order__user", "gateway")
    if user is not None:
        qs = qs.filter(order__user=user)
    if q:
        qs = qs.filter(Q(order__order_number__icontains=q) | Q(reference__icontains=q)
                       | Q(order__user__email__icontains=q))
    if status:
        qs = qs.filter(status=status)
    for p in qs.order_by("-created_at")[:LIMIT]:
        via = p.gateway.name if p.gateway else p.get_method_display()
        yield {
            "date": p.paid_at or p.created_at, "kind": "payment", "kind_label": "Order payment",
            "title": f"Order {p.order.order_number}", "detail": via,
            "reference": p.reference or p.tracker, "amount": p.amount,
            "sign": "-" if p.status != "refunded" else "+",
            "status": p.status, "status_label": p.get_status_display(),
            "user": p.order.user, "obj_id": p.pk, "order": p.order,
        }


def _wallet(user=None, q="", status=""):
    from Web.models import UserWalletTransaction
    if status:
        return
    qs = UserWalletTransaction.objects.select_related("user", "order")
    if user is not None:
        qs = qs.filter(user=user)
    if q:
        qs = qs.filter(Q(description__icontains=q) | Q(user__email__icontains=q) | Q(order__order_number__icontains=q))
    for t in qs.order_by("-created_at")[:LIMIT]:
        credit = t.transaction_type in ("credit", "returnorder")
        yield {
            "date": t.created_at, "kind": "wallet",
            "kind_label": "Wallet refund" if t.transaction_type == "returnorder" else
            ("Wallet credit" if credit else "Wallet debit"),
            "title": (t.description or t.get_transaction_type_display())[:120],
            "detail": f"Order {t.order.order_number}" if t.order else "",
            "reference": "", "amount": t.amount, "sign": "+" if credit else "-",
            "status": "done", "status_label": "Completed", "user": t.user, "obj_id": t.pk, "order": t.order,
        }


def _withdrawals(user=None, q="", status=""):
    from Web.models import WithdrawalRequest
    qs = WithdrawalRequest.objects.select_related("user")
    if user is not None:
        qs = qs.filter(user=user)
    if q:
        qs = qs.filter(Q(account_title__icontains=q) | Q(account_number__icontains=q)
                       | Q(gateway_reference__icontains=q) | Q(user__email__icontains=q))
    if status:
        qs = qs.filter(status=status)
    for w in qs.order_by("-requested_at")[:LIMIT]:
        detail = f"to {w.account_title} ({w.get_method_display()})"
        if w.fee:
            detail += f" - charge Rs {w.fee:,.2f}, sent Rs {w.payout_amount:,.2f}"
        yield {
            "date": w.processed_at or w.requested_at, "kind": "withdrawal", "kind_label": "Withdrawal",
            "title": f"Withdrawal #{w.pk}", "detail": detail, "reference": w.gateway_reference,
            "amount": w.amount, "sign": "-", "status": w.status, "status_label": w.get_status_display(),
            "user": w.user, "obj_id": w.pk, "order": None,
        }


def rows(user=None, kind="", q="", status=""):
    sources = {"payment": _payments, "wallet": _wallet, "withdrawal": _withdrawals}
    picked = [sources[kind]] if kind in sources else list(sources.values())
    out = [r for fn in picked for r in (fn(user=user, q=q, status=status) or [])]
    out.sort(key=lambda r: r["date"], reverse=True)
    return out


def totals(user=None):
    """Headline numbers for the history page."""
    from django.db.models import Sum

    from Web.models import UserWalletTransaction, WithdrawalRequest

    from .models import Payment
    pay = Payment.objects.filter(status="paid")
    wal = UserWalletTransaction.objects.all()
    wd = WithdrawalRequest.objects.filter(status="paid")
    if user is not None:
        pay, wal, wd = pay.filter(order__user=user), wal.filter(user=user), wd.filter(user=user)
    z = Decimal("0")
    return {
        "paid": pay.aggregate(s=Sum("amount"))["s"] or z,
        "wallet_in": wal.filter(transaction_type__in=["credit", "returnorder"]).aggregate(s=Sum("amount"))["s"] or z,
        "withdrawn": wd.aggregate(s=Sum("amount"))["s"] or z,
        "fees": wd.aggregate(s=Sum("fee"))["s"] or z,
    }
