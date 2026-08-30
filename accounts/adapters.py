from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.contrib.auth import get_user_model
from django.shortcuts import redirect

User = get_user_model()


class MySocialAccountAdapter(DefaultSocialAccountAdapter):

    def populate_user(self, request, sociallogin, data):
        user = super().populate_user(request, sociallogin, data)

        user.full_name = data.get("name", "")

        return user

    def pre_social_login(self, request, sociallogin):

        # Google account is already connected to a Django user
        if sociallogin.is_existing:
            return

        email = sociallogin.user.email

        if not email:
            return

        try:
            existing_user = User.objects.get(email__iexact=email)

            # User already has a password = manually registered account
            if existing_user.has_usable_password():

                return redirect(
                    "manual-account-login-required"
                )

            # Existing account has no usable password.
            # This is likely a social-created account, so connect Google.
            sociallogin.connect(request, existing_user)

        except User.DoesNotExist:
            # No existing account -> allauth will create the user
            pass