from django.shortcuts import render

# Create your views here.
from rest_framework.views import APIView
from rest_framework.response import Response
from django.db.models import Sum, F
from django.db.models.functions import TruncDate
from datetime import datetime
from Web.models import OrderItem,Order



class SalesReportAPIView(APIView):

    def get(self, request):
        start_date = request.GET.get("start_date")
        end_date = request.GET.get("end_date")

        items = OrderItem.objects.select_related('product', 'order')

        if start_date and end_date:
            items = items.filter(order__created_at__date__range=[start_date, end_date])

        # 🔹 Sales by Product
        product_sales = items.values(
            'product__name'
        ).annotate(
            total_qty=Sum('quantity'),
            total_sales=Sum(F('quantity') * F('price'))
        )

        # 🔹 Sales by Category
        category_sales = items.values(
            'product__category__name'
        ).annotate(
            total_qty=Sum('quantity'),
            total_sales=Sum(F('quantity') * F('price'))
        )

        # 🔹 Sales by Date
        date_sales = items.annotate(
            date=TruncDate('order__created_at')
        ).values('date').annotate(
            total_sales=Sum(F('quantity') * F('price'))
        ).order_by('date')

        return Response({
            "product_sales": product_sales,
            "category_sales": category_sales,
            "date_sales": date_sales
        })

def SalesReport(request):
    return render(request, "salesreport.html")

def InventoryReport(request):
    return render(request, "inventoryreport.html")

def CustomerAnalytics(request):
    return render(request, "customeranalytics.html")

def RevenueProfit(request):
    return render(request, "revenueprofit.html")

def OrderStats(request):
    return render(request, "orderstats.html")

from django.db.models import F
from products.models import Product
class InventoryReportAPIView(APIView):

    def get(self, request):

        low_stock_threshold = int(request.GET.get("threshold", 10))

        # Low Stock
        low_stock = Product.objects.filter(
            stock_quantity__gt=0,
            stock_quantity__lte=low_stock_threshold
        ).values(
            'name', 'sku', 'stock_quantity'
        )

        # Out of Stock
        out_of_stock = Product.objects.filter(
            stock_quantity=0
        ).values(
            'name', 'sku', 'stock_quantity'
        )

        return Response({
            "low_stock": list(low_stock),
            "out_of_stock": list(out_of_stock)
        })

from django.db.models import Sum, Count

class CustomerAnalyticsAPIView(APIView):

    def get(self, request):

        # 🔹 Top Buyers (by total spent)
        top_buyers = Order.objects.values(
            'user__full_name'
        ).annotate(
            total_spent=Sum('total_amount'),
            total_orders=Count('id')
        ).order_by('-total_spent')[:10]

        # 🔹 Repeat Customers (>1 orders)
        repeat_customers = Order.objects.values(
            'user__full_name'
        ).annotate(
            total_orders=Count('id'),
            total_spent=Sum('total_amount')
        ).filter(total_orders__gt=1).order_by('-total_orders')

        return Response({
            "top_buyers": list(top_buyers),
            "repeat_customers": list(repeat_customers)
        })



class RevenueProfitAPIView(APIView):

    def get(self, request):

        start_date = request.GET.get("start_date")
        end_date = request.GET.get("end_date")

        items = OrderItem.objects.select_related('product', 'order')

        if start_date and end_date:
            items = items.filter(order__created_at__date__range=[start_date, end_date])

        # 🔹 Overall Totals
        summary = items.aggregate(
            revenue=Sum(F('quantity') * F('price')),
            cost=Sum(F('quantity') * F('product__other_product_cost'))
        )

        revenue = summary['revenue'] or 0
        cost = summary['cost'] or 0
        profit = revenue - cost

        # 🔹 By Product
        product_data = items.values(
            'product__name'
        ).annotate(
            revenue=Sum(F('quantity') * F('price')),
            cost=Sum(F('quantity') * F('product__other_product_cost'))
        )

        for p in product_data:
            p['profit'] = (p['revenue'] or 0) - (p['cost'] or 0)

        # 🔹 By Date
        date_data = items.annotate(
            date=TruncDate('order__created_at')
        ).values('date').annotate(
            revenue=Sum(F('quantity') * F('price')),
            cost=Sum(F('quantity') * F('product__other_product_cost'))
        ).order_by('date')

        for d in date_data:
            d['profit'] = (d['revenue'] or 0) - (d['cost'] or 0)

        return Response({
            "summary": {
                "revenue": revenue,
                "cost": cost,
                "profit": profit
            },
            "product_data": list(product_data),
            "date_data": list(date_data)
        })



class OrderStatsAPIView(APIView):

    def get(self, request):

        start_date = request.GET.get("start_date")
        end_date = request.GET.get("end_date")

        orders = Order.objects.all()

        if start_date and end_date:
            orders = orders.filter(created_at__date__range=[start_date, end_date])

        # 🔹 Status Counts
        status_counts = orders.values('status').annotate(
            count=Count('id')
        )

        # 🔹 Daily Stats
        daily_stats = orders.annotate(
            date=TruncDate('created_at')
        ).values('date', 'status').annotate(
            count=Count('id')
        ).order_by('date')

        return Response({
            "status_counts": list(status_counts),
            "daily_stats": list(daily_stats)
        })