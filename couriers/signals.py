"""Auto-booking: when an order reaches the default courier's trigger status,
queue a booking task (after the transaction commits)."""
from django.db import transaction
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from Web.models import Order

from .models import CourierProvider, Shipment


@receiver(pre_save, sender=Order)
def _remember_old_status(sender, instance, **kwargs):
    if instance.pk:
        instance._old_status = (Order.objects.filter(pk=instance.pk)
                                .values_list("status", flat=True).first())
    else:
        instance._old_status = None


@receiver(post_save, sender=Order)
def _auto_book(sender, instance, created, **kwargs):
    old = getattr(instance, "_old_status", None)
    if old == instance.status:
        return
    provider = CourierProvider.objects.filter(is_default=True, is_active=True,
                                              auto_book_enabled=True).first()
    if not provider or instance.status != provider.auto_book_on_status:
        return
    if (instance.payment_method or "").lower() not in provider.auto_book_methods():
        return
    if Shipment.active_for(instance):
        return
    from .tasks import auto_book_order
    order_id = instance.pk
    transaction.on_commit(lambda: auto_book_order.delay(order_id))
