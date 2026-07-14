from django.urls import path,include
from .views import (
    EmailRegisterView,
    VerifyEmailView,
    ResendVerificationEmailView,
    login_view,register_view, logout_view,users_page,login_api,register_api
)
from .auth_views import EmailVerifiedTokenObtainPairView

from rest_framework.routers import DefaultRouter
from .views import UserViewSet

router = DefaultRouter()
router.register(r'users', UserViewSet)
urlpatterns = [
    path('', include(router.urls)),
    path('auth/register/email', EmailRegisterView.as_view()),
    path('auth/login', EmailVerifiedTokenObtainPairView.as_view()),
    path('auth/verify-email/<uuid:token>/', VerifyEmailView.as_view()),
    path('auth/resend-verification', ResendVerificationEmailView.as_view()),
    path("login/", login_view, name="login"),
    path("loginapi/", login_api, name="login_api"),
    path("register/", register_view, name="register"),
    path("registerapi/", register_api, name="register_api"),
    path("logout/", logout_view, name="logout"),
    path("users-page/", users_page, name="users-page"),

]
