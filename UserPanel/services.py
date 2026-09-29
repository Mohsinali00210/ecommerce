from decimal import Decimal
from django.db import transaction
from django.utils import timezone

from Web.models import UserWallet, UserWalletTransaction, WithdrawalRequest
from .payouts import send_payout, PayoutError

MIN_WITHDRAWAL = Decimal("500.00")


@transaction.atomic
def create_withdrawal(user, data):
    # lock the wallet row so two simultaneous requests can't overspend
    wallet = UserWallet.objects.select_for_update().get(user=user)
    amount = data["amount"]

    if amount < MIN_WITHDRAWAL:
        raise ValueError(f"Minimum withdrawal is Rs. {MIN_WITHDRAWAL}")
    if amount > wallet.balance:
        raise ValueError("Insufficient wallet balance.")

    wallet.balance -= amount
    wallet.save(update_fields=["balance"])

    hold = UserWalletTransaction.objects.create(
        user=user, wallet=wallet, transaction_type="debit", amount=amount,
        description="Withdrawal request (pending)",
    )
    return WithdrawalRequest.objects.create(
        user=user, wallet=wallet, amount=amount,
        method=data["method"], account_title=data["account_title"],
        account_number=data["account_number"], bank_name=data.get("bank_name", ""),
        hold_transaction=hold,
    )


def approve_withdrawal(withdrawal_id, admin_user):
    """Returns (ok: bool, message: str)"""
    with transaction.atomic():
        w = WithdrawalRequest.objects.select_for_update().get(pk=withdrawal_id)
        if w.status not in ("pending", "failed"):
            return False, "This request has already been processed."

        try:
            result = send_payout(w)          # <-- gateway call happens here
        except PayoutError as e:
            w.status = "failed"
            w.admin_note = str(e)
            w.save(update_fields=["status", "admin_note"])
            return False, f"Payout failed: {e}"

        w.status = "paid"
        w.gateway_reference = result.get("reference", "")
        w.processed_by = admin_user
        w.processed_at = timezone.now()
        w.save()

        if w.hold_transaction:
            w.hold_transaction.description = f"Withdrawal #{w.pk} to {w.get_method_display()} (paid)"
            w.hold_transaction.save(update_fields=["description"])
    return True, "Withdrawal approved and paid."


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
    return True, "Withdrawal rejected and amount refunded to wallet."