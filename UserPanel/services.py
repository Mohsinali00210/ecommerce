from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from Web.models import UserWallet, UserWalletTransaction, WithdrawalRequest

from .payouts import PayoutError, method_for, send_payout

MIN_WITHDRAWAL = Decimal("500.00")  # fallback when a method has no PayoutMethod row


def _log(w, kind, ok=False, user=None, message="", reference="", provider="", amount=None, data=None):
    from payments.models import PayoutEvent
    return PayoutEvent.objects.create(withdrawal=w, kind=kind, ok=ok, created_by=user, message=(message or "")[:500],
                                      reference=(reference or "")[:120], provider=provider,
                                      amount=amount if amount is not None else w.amount, data=data or {})


def enabled_methods():
    """PayoutMethod rows customers may pick (falls back to every method when none are set up)."""
    from payments.models import PayoutMethod
    rows = list(PayoutMethod.objects.filter(is_enabled=True))
    return rows


def quote(method, amount):
    """Fee preview for the withdraw page: {fee, net, min, max, fee_text, ...}."""
    amount = Decimal(amount or 0)
    pm = method_for(method)
    if pm is None:
        return {"fee": Decimal("0.00"), "net": amount, "min": MIN_WITHDRAWAL, "max": None, "fee_text": "Free",
                "processing_time": "within 2 working days"}
    fee = pm.fee_for(amount)
    return {"fee": fee, "net": amount - fee, "min": pm.min_amount, "max": pm.max_amount, "fee_text": pm.fee_text(),
            "processing_time": pm.processing_time}


@transaction.atomic
def create_withdrawal(user, data):
    # lock the wallet row so two simultaneous requests can't overspend
    wallet = UserWallet.objects.select_for_update().get(user=user)
    amount = Decimal(data["amount"])
    method = data["method"]
    pm = method_for(method)

    if pm is not None and not pm.is_enabled:
        raise ValueError("This withdrawal method is not available right now.")
    q = quote(method, amount)
    if amount < q["min"]:
        raise ValueError(f"Minimum withdrawal is Rs. {q['min']:,.2f}")
    if q["max"] is not None and amount > q["max"]:
        raise ValueError(f"Maximum withdrawal for this method is Rs. {q['max']:,.2f}")
    if amount > wallet.balance:
        raise ValueError("Insufficient wallet balance.")
    if q["net"] <= 0:
        raise ValueError("The amount must be more than the withdrawal charge.")

    wallet.balance -= amount
    wallet.save(update_fields=["balance"])

    desc = "Withdrawal request (pending)"
    if q["fee"] > 0:
        desc += f" - charge Rs {q['fee']:,.2f}, you receive Rs {q['net']:,.2f}"
    hold = UserWalletTransaction.objects.create(
        user=user, wallet=wallet, transaction_type="debit", amount=amount, description=desc,
    )
    w = WithdrawalRequest.objects.create(
        user=user, wallet=wallet, amount=amount, fee=q["fee"], net_amount=q["net"],
        method=method, account_title=data["account_title"],
        account_number=data["account_number"], bank_name=data.get("bank_name", ""),
        hold_transaction=hold,
    )
    _log(w, "requested", ok=True, user=user, message=f"fee {q['fee']}, net {q['net']}",
         data={"fee": str(q["fee"]), "net": str(q["net"]), "fee_rule": q["fee_text"]})
    return w


def approve_withdrawal(withdrawal_id, admin_user, reference="", note=""):
    """Sends the money (automatic methods) or records the manual transfer reference.
    Returns (ok: bool, message: str)."""
    with transaction.atomic():
        w = WithdrawalRequest.objects.select_for_update().get(pk=withdrawal_id)
        if w.status == "processing":
            # The provider accepted it earlier; staff confirm it has arrived.
            if not (reference or w.gateway_reference):
                return False, "Enter the provider's transaction reference to confirm this payout."
            result = {"reference": reference or w.gateway_reference, "status": "paid", "provider": "manual"}
        elif w.status not in ("pending", "failed"):
            return False, "This request has already been processed."
        else:
            pm = method_for(w.method)
            _log(w, "payout_attempt", ok=True, user=admin_user, amount=w.payout_amount,
                 provider=(pm.provider if pm and pm.automatic else "manual"))
            try:
                result = send_payout(w, reference=reference)  # <-- gateway call happens here
            except PayoutError as e:
                w.status = "failed"
                w.admin_note = str(e)[:1000]
                w.save(update_fields=["status", "admin_note"])
                _log(w, "payout_failed", user=admin_user, message=str(e), amount=w.payout_amount,
                     provider=(pm.provider if pm else ""), data=getattr(e, "data", {}))
                return False, f"Payout failed: {e}"

        w.gateway_reference = (result.get("reference") or "")[:120]
        w.processed_by = admin_user
        w.processed_at = timezone.now()
        if note:
            w.admin_note = note[:1000]
        if result.get("status") == "processing":
            w.status = "processing"
            w.save()
            _log(w, "payout_processing", ok=True, user=admin_user, reference=w.gateway_reference,
                 provider=result.get("provider", ""), amount=w.payout_amount, data=result.get("data", {}))
            return True, "Payout sent to the provider; it is processing. Confirm it once it has arrived."

        w.status = "paid"
        w.save()
        _log(w, "payout_paid", ok=True, user=admin_user, reference=w.gateway_reference,
             provider=result.get("provider", ""), amount=w.payout_amount, data=result.get("data", {}))

        if w.hold_transaction:
            fee_txt = f" (charge Rs {w.fee:,.2f}, sent Rs {w.payout_amount:,.2f})" if w.fee else ""
            w.hold_transaction.description = (f"Withdrawal #{w.pk} to {w.get_method_display()} (paid){fee_txt}"
                                              f"{' ref ' + w.gateway_reference if w.gateway_reference else ''}")[:255]
            w.hold_transaction.save(update_fields=["description"])
    return True, f"Withdrawal approved: Rs {w.payout_amount:,.2f} sent to {w.account_title}."


@transaction.atomic
def reject_withdrawal(withdrawal_id, admin_user, note=""):
    w = WithdrawalRequest.objects.select_for_update().get(pk=withdrawal_id)
    if w.status not in ("pending", "failed"):
        return False, "This request has already been processed."

    wallet = UserWallet.objects.select_for_update().get(pk=w.wallet_id)
    wallet.balance += w.amount
    wallet.save(update_fields=["balance"])

    UserWalletTransaction.objects.create(
        user=w.user, wallet=wallet, transaction_type="credit", amount=w.amount,
        description=f"Refund: withdrawal #{w.pk} rejected",
    )
    w.status = "rejected"
    w.admin_note = note
    w.processed_by = admin_user
    w.processed_at = timezone.now()
    w.save()
    _log(w, "rejected", ok=True, user=admin_user, message=note)
    return True, "Withdrawal rejected and amount refunded to wallet."
