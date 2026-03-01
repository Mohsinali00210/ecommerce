from django.conf import settings
from django.conf.urls.static import static
from django.urls import path, include
from .views import toggle_wishlist,ProductReviewCreateAPIView,OrderRequestAPIView,OrderDetailAPIView,Contact,MyOrders,PlaceOrderAPIView,AddressAPIView,SaveCheckoutSession,OrderSuccess,CheckoutPage,MyCart,Index,ProductDetails,AddToCartAPIView,CartDetailAPIView,RemoveCartItemAPIView,SaveCheckoutSession,CheckoutPage
urlpatterns = [
    path("", Index, name="Home"),
    path("Product/<int:id>/", ProductDetails, name="ProductDetails"),
    path("AddToCart/", AddToCartAPIView.as_view(), name="AddToCart"),
    path("CartDetail/", CartDetailAPIView.as_view(), name="CartDetail"),
    path("RemoveCartItem/", RemoveCartItemAPIView.as_view(), name="RemoveCartItem"),
    path("Cart/", MyCart, name="Cart"),
    path("SaveCheckoutSession/", SaveCheckoutSession, name="SaveCheckoutSession"),
    path("OrderSuccess/", OrderSuccess, name="OrderSuccess"),
    path("CheckoutPage/", CheckoutPage, name="CheckoutPage"),
    path("address/", AddressAPIView.as_view(), name="add_address"),
    path("address/<int:pk>/", AddressAPIView.as_view(), name="update_address"),
    path("place-order/", PlaceOrderAPIView.as_view(), name="place_order"),
    path("MyOrders/", MyOrders, name="MyOrders"),
    path("Contact/", Contact, name="Contact"),
    path("OrderDetailApi/<int:pk>/", OrderDetailAPIView.as_view(), name="OrderDetailApi"),
    path('order-request/', OrderRequestAPIView.as_view(), name='order-request'),
    path("review/",ProductReviewCreateAPIView.as_view(),name="ProductReviewCreate"),
    path("wishlisttoggle/<int:product_id>/", toggle_wishlist, name="toggle_wishlist"),
]

if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
