from django.conf import settings
from django.conf.urls.static import static
from django.urls import path, include
from .views import PromotionDetail,wish_to_buy,get_cat,get_messages,send_message,cart_drawer,get_token_for_logged_in_user,UserCartCountAPIView,product_list,UserNotificationAPIView,toggle_wishlist,ProductReviewCreateAPIView,OrderRequestAPIView,OrderDetailAPIView,Contact,MyOrders,PlaceOrderAPIView,AddressAPIView,SaveCheckoutSession,OrderSuccess,CheckoutPage,MyCart,Index,ProductDetails,AddToCartAPIView,CartDetailAPIView,RemoveCartItemAPIView,SaveCheckoutSession,CheckoutPage
from accounts.views import profile_view,update_profile_ajax
urlpatterns = [
    path("", Index, name="Home"),
    path("Product/<int:id>/", ProductDetails, name="ProductDetails"),
    path("AddToCart/", AddToCartAPIView.as_view(), name="AddToCart"),
    path("cart_drawer/", cart_drawer, name="cart_drawer"),
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
    path("notifications/", UserNotificationAPIView.as_view(), name="notifications"),
    path("profile/", profile_view, name="profile"),
        path('ajax/update-profile/', update_profile_ajax, name='update_profile_ajax'),
        path('product_list/', product_list, name='product_list'),
        path('User_Cart_Count/', UserCartCountAPIView.as_view(), name='User_Cart_Count'),
    path('get-my-token/', get_token_for_logged_in_user, name='get_my_token'),
    path("send/", send_message, name="send_message"),
    path("messages/<int:product_id>/", get_messages, name="get_messages"),
    path("get_cat/", get_cat, name="get_cat"),
        path("wish-to-buy/", wish_to_buy, name="wish_to_buy"),
        path("promo/<int:id>/", PromotionDetail, name="promo"),

]

if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
