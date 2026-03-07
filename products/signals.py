from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone
from .models import Promotion
from Web.models import Notification, NotificationRecipient
from django.contrib.auth import get_user_model

User = get_user_model()

@receiver(post_save, sender=Promotion)
def promotion_created_notification(sender, instance, created, **kwargs):
    if created:  # Only when new promotion is created
        
        notification = Notification.objects.create(
            title="New Promotion Available 🎉",
            message=f"A new promotion '{instance.name}' is now available.",
            notification_type="promotion",
            is_general=True,
            is_active=True
        )

        # Send to all users (or adjust as needed)
        users = User.objects.filter(is_active=True)

        recipients = [
            NotificationRecipient(
                notification=notification,
                user=user,
                is_read=False
            )
            for user in users
        ]

        NotificationRecipient.objects.bulk_create(recipients)