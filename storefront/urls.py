from django.contrib.sitemaps import views as sitemap_views
from django.urls import path, re_path

from . import admin_views, public_views
from .sitemaps import SITEMAPS

# Mounted at /Adminpanel/Storefront/
admin_urlpatterns = [
    path("home-features/", admin_views.home_features, name="storefront_home_features"),
    path("seo/", admin_views.seo_settings, name="storefront_seo"),
    path("seo/tool/<slug:action>/", admin_views.seo_tool, name="storefront_seo_tool"),
    path("seo/merchant/preview/<int:pk>/", admin_views.merchant_preview, name="storefront_merchant_preview"),
]

# Mounted at the site root
public_urlpatterns = [
    path("robots.txt", public_views.robots_txt, name="robots_txt"),
    path("sitemap.xml", public_views.sitemap_index, name="storefront_sitemap"),
    path("sitemap-<section>.xml", sitemap_views.sitemap,
         {"sitemaps": SITEMAPS}, name="storefront_sitemap_section"),
    path("feeds/google-merchant.xml", public_views.google_merchant_feed, name="storefront_merchant_feed"),
    re_path(r"^(?P<key>[A-Za-z0-9-]{8,128})\.txt$", public_views.indexnow_key, name="indexnow_key"),
]
