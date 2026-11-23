from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from couriers.urls import public_urls as courier_public_urls
from Web.views_public import order_public
from payments.urls import admin_urlpatterns as payment_admin_urls
from storefront.urls import admin_urlpatterns as storefront_admin_urls
from storefront.urls import public_urlpatterns as storefront_public_urls

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/v1/', include('accounts.urls')),
    path('Adminpanel/Products/', include('products.urls')),
    path('Adminpanel/Reports/', include('reports.urls')),
    path('Adminpanel/Couriers/', include('couriers.urls')),
    path('Adminpanel/Payments/', include(payment_admin_urls)),
    path('Adminpanel/Storefront/', include(storefront_admin_urls)),
    path('Adminpanel/', include('adminpanel.urls')),
    path('couriers/', include(courier_public_urls)),
    path('order/view/<str:token>/', order_public, name='order_public'),
    path('payments/', include('payments.urls')),
    path('chat/', include('chat.urls')),
    path('web', include('Web.urls')),
    path("", include(storefront_public_urls)),   # robots.txt, sitemap.xml, merchant feed, IndexNow key
    path("", include("UserPanel.urls")),
    # The duplicate "userpanel" include was removed: it registered the "home"
    # namespace twice (nothing linked to /userpanel...).

    path("api/token/", TokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("api/token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path('accounts/', include('allauth.urls')),
]
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

handler400 = "adminpanel.views.error_400"
handler403 = "adminpanel.views.error_403"
handler404 = "adminpanel.views.error_404"
handler500 = "adminpanel.views.error_500"
