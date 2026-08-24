from django.urls import path
from . import views

app_name = "home"

urlpatterns = [
    path("", views.home, name="home"),
     path("product/<slug:slug>/", views.ProductDetails, name="Product_Details"),
    path("product/<slug:slug>/<str:sku>/", views.ProductDetails, name="Product_Details"), 
    path("CheckoutPage/", views.CheckoutPage, name="MyCheckoutPage"), 
    path("MyCart/", views.MyCart, name="MyCart"), 
        path("Orders/", views.MyOrders, name="Orders"),
        path("orderdetail/<str:order_number>/", views.OrderDetail, name="order-detail"),
        path("Wishlist/", views.Wishlist, name="Wishlist"),
        path("wish-to-buy/", views.wish_to_buy, name="wish-to-buy"),
        path("search-products/", views.search_products, name="search-products"),
        path("best-deals/", views.best_deals, name="best-deals"),
        path("user-profile/", views.profile, name="user-profile"),
        path("edit-profile/", views.edit_profile, name="edit-profile"),
        path("user-wallet/", views.wallet_view, name="user-wallet"),
        path("address-set-default/<int:address_id>/", views.address_set_default, name="address-set-default"),
        path("address-delete/<int:address_id>/", views.address_delete, name="address-delete"),
        path("address-save/", views.address_save, name="address-save"),
        path("address-detail/<int:address_id>/", views.address_detail, name="address-detail"),
        path("user-address/", views.addresses, name="user-address"),
        path("Contact/", views.Contact, name="Contact"),
        path("blog-detail/<slug:slug>/", views.blog_detail, name="blog-detail"),
        path("blog/", views.blog_list, name="blog"),

]

# In your project urls.py:
#   from django.urls import include, path
#   urlpatterns = [
#       ...
#       path("", include("home.urls")),
#   ]
