from django.core.mail import send_mail
from django.conf import settings


def send_verification_email(user):
    verification_url = (
        f"http://localhost:8000/api/v1/auth/verify-email/"
        f"{user.email_verification_token}/"
    )

    send_mail(
        subject="Verify Your Email",
        message=f"Click the link to verify your email:\n{verification_url}",
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user.email],
        fail_silently=False,
    )
