class PayoutError(Exception):
    pass


def send_payout(withdrawal):
    """
    Send money to the user's account. Called when admin clicks Approve.
    Must return a dict like {"reference": "<gateway payout id>"}.
    Must raise PayoutError if the gateway rejects or fails.
    """
    method = withdrawal.method

    if method == "jazzcash":
        # TODO: call JazzCash API here
        # response = jazzcash_client.disburse(
        #     mobile=withdrawal.account_number,
        #     amount=withdrawal.amount,
        #     ref=f"WD-{withdrawal.pk}",
        # )
        pass
    elif method == "easypaisa":
        # TODO: call Easypaisa API here
        pass
    elif method == "stripe":
        # TODO: call Stripe payout/transfer here
        pass
    elif method == "bank":
        # TODO: call bank transfer API here (or mark for manual transfer)
        pass

    # Placeholder result, replace with the real gateway response
    return {"reference": f"TEST-{withdrawal.pk}"}