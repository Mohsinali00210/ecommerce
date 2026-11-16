from django.urls import path

from . import views

app_name = "payments"

urlpatterns = [
    path("pay/<str:token>/", views.pay, name="pay"),
    path("<int:pk>/return/", views.payment_return, name="return"),
    path("<int:pk>/cancel/", views.payment_cancel, name="cancel"),
    path("<int:pk>/proof/", views.upload_proof, name="upload_proof"),
    path("<int:pk>/proof/view/", views.view_proof, name="view_proof"),
    path("webhook/<slug:code>/", views.webhook, name="webhook"),
]


from . import admin_views  # noqa: E402

admin_urlpatterns = [
    path("", admin_views.payments_list, name="admin_payments"),
    path("<int:pk>/", admin_views.payment_detail, name="admin_payment_detail"),
    path("<int:pk>/action/", admin_views.payment_action, name="admin_payment_action"),
    path("gateway/", admin_views.gateway_settings, name="admin_payment_gateway"),
]
