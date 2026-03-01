from django.urls import path
from .views import (
    EmailRegisterView,
    VerifyEmailView,
    ResendVerificationEmailView,
    login_view,register_view, logout_view
)
from .auth_views import EmailVerifiedTokenObtainPairView

urlpatterns = [
    path('auth/register/email', EmailRegisterView.as_view()),
    path('auth/login', EmailVerifiedTokenObtainPairView.as_view()),
    path('auth/verify-email/<uuid:token>/', VerifyEmailView.as_view()),
    path('auth/resend-verification', ResendVerificationEmailView.as_view()),
    path("login/", login_view, name="login"),
    path("register/", register_view, name="register"),
    path("logout/", logout_view, name="logout"),

]
