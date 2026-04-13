from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.contrib.auth import get_user_model

User = get_user_model()


class MySocialAccountAdapter(DefaultSocialAccountAdapter):

    def populate_user(self, request, sociallogin, data):
        user = super().populate_user(request, sociallogin, data)
        user.full_name = data.get('name', '')
        return user

    def pre_social_login(self, request, sociallogin):
        if sociallogin.is_existing:
            return
        email = sociallogin.user.email
        if not email:
            return
        try:
            existing_user = User.objects.get(email=email)
            sociallogin.connect(request, existing_user)
        except User.DoesNotExist:
            pass