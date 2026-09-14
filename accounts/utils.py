# from django.core.mail import send_mail
# from django.conf import settings


# def send_verification_email(user):
#     verification_url = (
#         f"http://localhost:8000/api/v1/auth/verify-email/"
#         f"{user.email_verification_token}/"
#     )

#     send_mail(
#         subject="Verify Your Email",
#         message=f"Click the link to verify your email:\n{verification_url}",
#         from_email=settings.DEFAULT_FROM_EMAIL,
#         recipient_list=[user.email],
#         fail_silently=False,
#     )

import random
from datetime import timedelta

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.html import strip_tags

from .models import OTP  # adjust import path to match your app


def send_templated_email(to_email, subject, template_name, context=None):
    """
    Reusable email sender used across the whole app (password reset, order
    confirmations, promotions, etc.) — not just for this one flow.

    template_name is an HTML template path (e.g. "emails/reset_password_otp.html").
    A plain-text fallback is auto-derived by stripping tags, so you only ever
    maintain one template per email.
    """
    context = context or {}
    html_content = render_to_string(template_name, context)
    text_content = strip_tags(html_content)

    email = EmailMultiAlternatives(
        subject=subject,
        body=text_content,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[to_email],
    )
    email.attach_alternative(html_content, "text/html")
    email.send(fail_silently=False)


def generate_otp(user, purpose, minutes_valid=10):
    """
    Creates a fresh 6-digit OTP for (user, purpose), invalidating any earlier
    unused ones for that same purpose so only the most recent code works.
    """
    code = f"{random.randint(0, 999999):06d}"
    OTP.objects.filter(user=user, purpose=purpose).delete()
    return OTP.objects.create(
        user=user,
        code=code,
        purpose=purpose,
        expires_at=timezone.now() + timedelta(minutes=minutes_valid),
    )