from django.db.models import Exists, OuterRef

from Web.models import Order, OrderSeenLog


def admin_order_counts(request):
    unseen_orders_count = 0

    if request.user.is_authenticated and request.user.is_superuser:

        seen_orders = OrderSeenLog.objects.filter(
            user=request.user,
            order=OuterRef("pk"),
            is_seen_by_admin=True,
        )

        unseen_orders_count = (
            Order.objects
            .filter(user__isnull=False)
            .annotate(
                has_seen=Exists(seen_orders)
            )
            .filter(has_seen=False)
            .count()
        )

    return {
        "unseen_orders_count": unseen_orders_count,
    }