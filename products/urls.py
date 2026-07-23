from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import variant_bulk_create,product_list,product_form_view,variant_add_modal,variant_edit_modal,variant_delete,image_modal,image_delete,promotion_modal,promotion_modal,promotion_delete,tag_modal,tag_remove,wish_to_buy_admin,wish_to_buy_list,picture_page,PictureViewSet,OrdersByStatus,inventory_page,VariantInventoryViewSet,ProductVariantViewSet,promotions_page,PromotionsViewSet,wishlist_page,admin_reviews_page,AdminReviewListAPIView,AdminReviewUpdateAPIView,AdminOrderRequestUpdateAPIView,support_ticket_list_view,OrderDetailAPIView,OrderUpdateStatusAPIView,OrdersListAPIView,orders,ProductPreview,editProduct,products,addProduct,CategoryViewSet,categories,ProductAttributeViewSet,attributes,AttributeTypesViewSet,BrandViewSet,brands,ProductViewSet,PromotionViewSet 

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
    path("addProduct/<int:product_id>/",addProduct, name="editProduct" ),
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

    path("admin/wish-to-buy/", wish_to_buy_admin, name="wish_to_buy_admin"),
    path("api/wish-to-buy/", wish_to_buy_list, name="wish_to_buy_list"),


    

     path('products/', product_list, name='product_list'),
    path('products/add/', product_form_view, name='product_add'),
    path('products/<int:pk>/edit/', product_form_view, name='product_edit'),
 
    # Variants
    path('products/<int:product_id>/variants/add/', variant_add_modal, name='variant_add'),
    path('products/<int:product_id>/variants/bulk-add/', variant_bulk_create, name='variant_bulk_add'),
    path('products/<int:product_id>/variants/<int:variant_id>/edit/', variant_edit_modal, name='variant_edit'),
    path('products/<int:product_id>/variants/<int:variant_id>/delete/', variant_delete, name='variant_delete'),
 
    # Images
    path('products/<int:product_id>/images/add/', image_modal, name='image_add'),
    path('products/<int:product_id>/images/<int:image_id>/delete/', image_delete, name='image_delete'),
 
    # Promotions
    path('products/<int:product_id>/promotions/add/', promotion_modal, name='promotion_add'),
    path('products/<int:product_id>/promotions/<int:promotion_id>/edit/', promotion_modal, name='promotion_edit'),
    path('products/<int:product_id>/promotions/<int:promotion_id>/delete/', promotion_delete, name='promotion_delete'),
 
    # Tags
    path('products/<int:product_id>/tags/add/', tag_modal, name='tag_add'),
    path('products/<int:product_id>/tags/<int:tag_id>/remove/', tag_remove, name='tag_remove'),
]