"""Email the customer whenever an order's status changes."""
from django.db import transaction
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from .models import Order


@receiver(pre_save, sender=Order)
def _remember_status(sender, instance, **kwargs):
    instance._email_old_status = (Order.objects.filter(pk=instance.pk).values_list("status", flat=True).first()
                                  if instance.pk else None)


@receiver(post_save, sender=Order)
def _status_changed(sender, instance, created, **kwargs):
    old = getattr(instance, "_email_old_status", None)
    if created or old is None or old == instance.status or getattr(instance, "_skip_status_email", False):
        return
    from .order_emails import send_order_status_email
    oid, status = instance.pk, instance.status
    transaction.on_commit(lambda: send_order_status_email.delay(oid, status))
