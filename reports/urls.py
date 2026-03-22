from django.conf import settings
from django.conf.urls.static import static
from django.urls import path, include
from .views import OrderStatsAPIView,OrderStats,RevenueProfitAPIView,RevenueProfit,SalesReportAPIView,SalesReport,InventoryReport,InventoryReportAPIView,CustomerAnalytics,CustomerAnalyticsAPIView
urlpatterns = [
    path('get-sales-report/', SalesReportAPIView.as_view(),name='get_sales_report'),
    path('sales-report/', SalesReport,name='sales_report'),
    path('get-inventory-report/', InventoryReportAPIView.as_view(), name='get_inventory_report'),
    path('inventory-report/', InventoryReport,name='inventory_report'),
    path('get-customer-analytics/', CustomerAnalyticsAPIView.as_view(), name='get_customer_analytics'),
    path('customer-analytics/', CustomerAnalytics, name='customer_analytics'),

    path('get-revenue-profit/', RevenueProfitAPIView.as_view(), name='get_revenue_profit'),
    path('revenue-profit/', RevenueProfit, name='revenue_profit'),
    path('get-order-stats/', OrderStatsAPIView.as_view(), name='get_order_stats'),
    path('order-stats/', OrderStats, name='order_stats'),
]

if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
