from rest_framework import serializers
from Web.models import Notification,OrderItem,Order

from rest_framework.throttling import SimpleRateThrottle

class NotificationSerializer(serializers.ModelSerializer):

    class Meta:
        model = Notification
        fields = [
            "id",
            "title",
            "message",
            "notification_type",
            "is_read",
            "created_at",
        ]



 
# Order flow shown as a progress bar. cancelled / returned / failed are
# terminal states outside this flow and are shown on their own.
TRACK_STEPS = ["pending", "submited", "processing", "shipped", "delivered"]
 
 
# ---------------------------------------------------------------------------
# Serializers
# ---------------------------------------------------------------------------
class TrackOrderItemSerializer(serializers.ModelSerializer):
    product_name = serializers.SerializerMethodField()
    variant = serializers.SerializerMethodField()
    product_image = serializers.SerializerMethodField()
 
    class Meta:
        model = OrderItem  # noqa: F821
        fields = ["id", "product_name", "variant", "product_image", "quantity", "price", "total"]
 
    def get_product_name(self, obj):
        return obj.product.name if obj.product else "Product no longer available"
 
    def get_variant(self, obj):
        return str(obj.variant) if obj.variant else None
 
    def get_product_image(self, obj):
        if not obj.product:
            return None
        images = list(obj.product.images.all())  # uses the prefetch, no extra query
        if not images:
            return None
        url = images[0].image.url
        request = self.context.get("request")
        return request.build_absolute_uri(url) if request else url
 
 
class TrackOrderSerializer(serializers.ModelSerializer):
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    payment_method_label = serializers.CharField(source="get_payment_method_display", read_only=True)
    payment_status_label = serializers.CharField(source="get_payment_status_display", read_only=True)
    items = TrackOrderItemSerializer(many=True, read_only=True)
    timeline = serializers.SerializerMethodField()
    shipping_address = serializers.SerializerMethodField()
 
    class Meta:
        model = Order  # noqa: F821
        fields = [
            "order_number", "tracking_number",
            "status", "status_label",
            "payment_method_label", "payment_status_label",
            "placed_at", "delivered_at",
            "subtotal", "shipping_charges", "total_amount",
            "items", "timeline", "shipping_address",
        ]
 
    def get_timeline(self, obj):
        labels = dict(Order.ORDER_STATUS)  # noqa: F821
 
        # cancelled / returned / failed: show the single terminal state
        if obj.status not in TRACK_STEPS:
            return [{"key": obj.status, "label": labels.get(obj.status, obj.status), "state": "stopped"}]
 
        current = TRACK_STEPS.index(obj.status)
        delivered = obj.status == "delivered"
        steps = []
        for i, key in enumerate(TRACK_STEPS):
            if i < current or delivered:
                state = "done"
            elif i == current:
                state = "current"
            else:
                state = "upcoming"
            steps.append({"key": key, "label": labels[key], "state": state})
        return steps
 
    def get_shipping_address(self, obj):
        """Only the order's owner gets the address; anonymous lookups never see it."""
        request = self.context.get("request")
        user = getattr(request, "user", None)
        if not (user and user.is_authenticated and obj.user_id == user.id):
            return None
        a = obj.shipping_address
        if not a:
            return None
        return {
            "street_address": a.street_address,
            "city": a.city,
            "state": a.state,
            "country": a.country,
        }
 
 
# ---------------------------------------------------------------------------
# Throttle (order numbers are guessable-ish, so limit lookups per IP)
# ---------------------------------------------------------------------------
class TrackOrderThrottle(SimpleRateThrottle):
    scope = "track_order"
    rate = "20/min"  # set here so no DEFAULT_THROTTLE_RATES entry is needed
 
    def get_cache_key(self, request, view):
        return self.cache_format % {"scope": self.scope, "ident": self.get_ident(request)}