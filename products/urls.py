from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import picture_page,PictureViewSet,OrdersByStatus,inventory_page,VariantInventoryViewSet,ProductVariantViewSet,promotions_page,PromotionsViewSet,wishlist_page,admin_reviews_page,AdminReviewListAPIView,AdminReviewUpdateAPIView,AdminOrderRequestUpdateAPIView,support_ticket_list_view,OrderDetailAPIView,OrderUpdateStatusAPIView,OrdersListAPIView,orders,ProductPreview,editProduct,products,addProduct,CategoryViewSet,categories,ProductAttributeViewSet,attributes,AttributeTypesViewSet,BrandViewSet,brands,ProductViewSet,PromotionViewSet 

router = DefaultRouter()
router.register(r'categories', CategoryViewSet, basename='category')
router.register(r'attributes', ProductAttributeViewSet, basename='attribute')
router.register(r'attributetypes', AttributeTypesViewSet, basename='attributetypes')
router.register(r'brands', BrandViewSet, basename='brand')
router.register(r'products', ProductViewSet, basename='product')
router.register(r'promotions', PromotionViewSet, basename='promotion')
router.register(r'promotionss', PromotionsViewSet, basename='promotions')
router.register(r'product-variants', ProductVariantViewSet)
router.register(r'inventory', VariantInventoryViewSet)
router.register(r'pictures', PictureViewSet, basename='pictures')



urlpatterns = [
    path('api/v1/', include(router.urls)),
    path("categories/", categories, name="categories"),
    path("attributes/", attributes, name="attributes"),
    path("brands/", brands, name="brands"),
    path("addProduct/", addProduct, name="addProduct"),
    path("editProduct/<int:id>/", editProduct, name="editProduct"),
    path("products/", products, name="products"),
    path("ProductPreview/", ProductPreview, name="ProductPreview"),
    path("Orders/", orders, name="Orders"),
    path("OrdersByStatus/<str:status>/", OrdersByStatus, name="OrdersByStatus"),
    path("GetOrders/", OrdersListAPIView.as_view(), name="GetOrders"),
    path("orderdetail/<int:pk>/", OrderDetailAPIView.as_view(), name="orderdetail"),
    path("orderupdate/<int:pk>/", OrderUpdateStatusAPIView.as_view(), name="orderupdate"),
    path("support-tickets/", support_ticket_list_view, name="support_ticket_list"),
    path("AdminOrderRequestUpdate/<int:pk>/", AdminOrderRequestUpdateAPIView.as_view(), name="AdminOrderRequestUpdate"),
    # path("attributes/", attributes, name="attributetypes"),
    path("reviews/", AdminReviewListAPIView.as_view(), name="AdminReviewList"),
    path("reviews/<int:pk>/", AdminReviewUpdateAPIView.as_view(), name="AdminReviewUpdate"),
    path("reviews-page/", admin_reviews_page, name="AdminReviewsPage"),
    path("wishlist/", wishlist_page, name="wishlist"),
    path("promotions-page/", promotions_page, name="promotions_page"),
    path("inventory-page/", inventory_page, name="inventory-page"),
    path("picture-page/", picture_page, name="picture-page"),
]