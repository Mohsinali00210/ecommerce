from rest_framework import serializers
from .models import Cart, CartItem
from accounts.models import Address
from django.db import transaction
from django.utils import timezone
from .models import OrderRequest,Order, OrderItem
from products.models import Product, ProductVariant,Promotion
from django.core.exceptions import ValidationError
from decimal import Decimal

class CartItemSerializer(serializers.ModelSerializer):
    product_id = serializers.PrimaryKeyRelatedField(queryset=Product.objects.all(),source="product")
    variant_id = serializers.PrimaryKeyRelatedField(queryset=ProductVariant.objects.all(),source="variant",allow_null=True,required=False)

    class Meta:
        model = CartItem
        fields = ("id","product_id","variant_id","quantity","price",)
class CartSerializer(serializers.ModelSerializer):
    items = CartItemSerializer(many=True)

    class Meta:
        model = Cart
        fields = ("id","user","session_key","items",)
        read_only_fields = ("user", "session_key")


class AddressSerializer(serializers.ModelSerializer):
    class Meta:
        model = Address
        fields = [
            "id",
            "address_type",
            "full_name",
            "phone",
            "street_address",
            "city",
            "state",
            "country",
            "postal_code",
        ]

class OrderItemCreateSerializer(serializers.Serializer):
    product_id = serializers.IntegerField()
    variant_id = serializers.IntegerField(required=False, allow_null=True)
    quantity = serializers.IntegerField(min_value=1)

class CheckoutSerializer(serializers.Serializer):
    billing_address = AddressSerializer()
    shipping_address = AddressSerializer()
    items = OrderItemCreateSerializer(many=True)

    payment_method = serializers.ChoiceField(
        choices=Order.PAYMENT_METHODS,
        default="cod"
    )
    shipping_charges = serializers.DecimalField(
        max_digits=10, decimal_places=2, default=0
    )
    notes = serializers.CharField(required=False, allow_blank=True)

    def create(self, validated_data):
        user = self.context["request"].user

        billing_data = validated_data.pop("billing_address")
        shipping_data = validated_data.pop("shipping_address")
        items_data = validated_data.pop("items")

        with transaction.atomic():
            # Save addresses
            billing_address = Address.objects.create(
                user=user, address_type="billing", **billing_data
            )
            shipping_address = Address.objects.create(
                user=user, address_type="shipping", **shipping_data
            )

            # Create order
            order = Order.objects.create(
                user=user,
                billing_address=billing_address,
                shipping_address=shipping_address,
                payment_method=validated_data.get("payment_method", "cod"),
                shipping_charges=validated_data.get("shipping_charges", 0),
                notes=validated_data.get("notes", ""),
                status="pending",
            )

            total_amount = 0

            for item in items_data:
                product = Product.objects.get(id=item["product_id"])
                variant = None

                if item.get("variant_id"):
                    variant = ProductVariant.objects.get(id=item["variant_id"])

                # Apply promotion if exists
                promo = product.promotions.filter(
                    end_date__gte=timezone.now()
                ).first()

                price = (
                    promo.get_discounted_price(product.price)
                    if promo else product.price
                )

                order_item = OrderItem.objects.create(
                    order=order,
                    product=product,
                    variant=variant,
                    quantity=item["quantity"],
                    price=price,
                )

                total_amount += order_item.total

            order.total_amount = total_amount + order.shipping_charges
            order.save()

        return order




class AddressSerializer(serializers.ModelSerializer):
    class Meta:
        model = Address
        fields = [
            "id",
            "address_type",
            "full_name",
            "phone",
            "street_address",
            "city",
            "state",
            "country",
            "postal_code",
            "is_default",
        ]

    def validate_phone(self, value):
        if not value.isdigit():
            raise serializers.ValidationError("Phone number must contain only digits.")
        if len(value) < 10:
            raise serializers.ValidationError("Phone number is too short.")
        return value

    def validate(self, data):
        required_fields = [
            "full_name",
            "phone",
            "street_address",
            "city",
            "postal_code",
        ]
        for field in required_fields:
            if not data.get(field):
                raise serializers.ValidationError({field: "This field is required."})
        return data

class PlaceOrderSerializer(serializers.Serializer):
    address_id = serializers.IntegerField()

    checkout_items = serializers.ListField(
        child=serializers.DictField(),
        required=False
    )

    def validate_address_id(self, value):
        user = self.context["request"].user

        if not Address.objects.filter(
            id=value,
            user=user
        ).exists():
            raise serializers.ValidationError(
                "Invalid address."
            )

        return value

    @transaction.atomic
    def create(self, validated_data):

        request = self.context["request"]
        user = request.user

        # -------------------------------------------------
        # GET CHECKOUT ITEMS FROM SESSION
        # -------------------------------------------------

        checkout_items = request.session.get(
            "checkout_items",
            []
        )

        if not checkout_items:
            raise serializers.ValidationError(
                "No checkout items found."
            )

        # -------------------------------------------------
        # ADDRESS
        # -------------------------------------------------

        address = Address.objects.get(
            id=validated_data["address_id"],
            user=user
        )

        # -------------------------------------------------
        # PRODUCT / VARIANT IDS
        # -------------------------------------------------

        product_ids = []

        variant_ids = []

        for item in checkout_items:

            try:
                product_id = int(item["product_id"])
            except (KeyError, TypeError, ValueError):
                raise serializers.ValidationError(
                    "Invalid product information."
                )

            product_ids.append(product_id)

            if item.get("variant_id"):
                try:
                    variant_ids.append(
                        int(item["variant_id"])
                    )
                except (TypeError, ValueError):
                    raise serializers.ValidationError(
                        "Invalid variant information."
                    )

        # -------------------------------------------------
        # LOAD PRODUCTS
        # -------------------------------------------------

        products = Product.objects.filter(
            id__in=product_ids,
            status="active"
        )

        variants = ProductVariant.objects.filter(
            id__in=variant_ids
        )

        product_map = {
            product.id: product
            for product in products
        }

        variant_map = {
            variant.id: variant
            for variant in variants
        }

        # -------------------------------------------------
        # CURRENT TIME
        # -------------------------------------------------

        now = timezone.now()

        # -------------------------------------------------
        # CREATE ORDER
        # -------------------------------------------------

        shipping_charges = [
            p.shipping_charges or Decimal("0")
            for p in products
        ]

        max_shipping_charge = (
            max(shipping_charges)
            if shipping_charges
            else Decimal("0")
        )

        order = Order.objects.create(
            user=user,
            shipping_address=address,
            billing_address=address,
            payment_method="COD",
            shipping_charges=max_shipping_charge,
            status="pending",
        )

        subtotal = Decimal("0")
        total_items_created = 0

        # -------------------------------------------------
        # CREATE ORDER ITEMS
        # -------------------------------------------------

        for item in checkout_items:

            product_id = int(item["product_id"])

            product = product_map.get(product_id)

            # Product no longer exists / inactive
            if not product:
                raise serializers.ValidationError(
                    f"Product with ID {product_id} is no longer available."
                )

            # -------------------------------------------------
            # VARIANT
            # -------------------------------------------------

            variant = None

            if item.get("variant_id"):

                variant_id = int(item["variant_id"])

                variant = variant_map.get(variant_id)

                if not variant:
                    raise serializers.ValidationError(
                        f"Selected variant for {product.name} is no longer available."
                    )

                # Make sure variant belongs to this product
                if variant.product_id != product.id:
                    raise serializers.ValidationError(
                        "Invalid product variant."
                    )

            # -------------------------------------------------
            # QUANTITY
            # -------------------------------------------------

            try:
                qty = int(item.get("quantity", 1))
            except (TypeError, ValueError):

                raise serializers.ValidationError(
                    f"Invalid quantity for {product.name}."
                )

            if qty <= 0:
                raise serializers.ValidationError(
                    f"Invalid quantity for {product.name}."
                )

            # -------------------------------------------------
            # STOCK CHECK
            # -------------------------------------------------

            if variant:

                if hasattr(variant, "is_active"):
                    if not variant.is_active:
                        raise serializers.ValidationError(
                            f"Variant of {product.name} is inactive."
                        )

                if variant.stock_quantity < qty:
                    raise serializers.ValidationError(
                        f"Not enough stock available for {product.name}."
                    )

            else:

                if product.stock_quantity < qty:
                    raise serializers.ValidationError(
                        f"Not enough stock available for {product.name}."
                    )

            # -------------------------------------------------
            # BASE PRICE
            # -------------------------------------------------

            base_price = (
                variant.price
                if variant
                else product.price
            )

            base_price = Decimal(str(base_price))

            final_price = base_price

            # -------------------------------------------------
            # ACTIVE PROMOTION
            # -------------------------------------------------

            promo = (
                Promotion.objects
                .filter(
                    products=product,
                    start_date__lte=now,
                    end_date__gte=now,
                    is_active=True
                )
                .first()
            )

            if promo:

                final_price = promo.get_discounted_price(
                    base_price
                )

                final_price = Decimal(
                    str(final_price)
                )

            # -------------------------------------------------
            # CREATE ORDER ITEM
            # -------------------------------------------------

            OrderItem.objects.create(
                order=order,
                product=product,
                variant=variant,
                quantity=qty,
                price=final_price
            )

            subtotal += final_price * qty

            total_items_created += 1

        # -------------------------------------------------
        # MAKE SURE ORDER HAS ITEMS
        # -------------------------------------------------

        if total_items_created == 0:

            raise serializers.ValidationError(
                "No valid products found for checkout."
            )

        # -------------------------------------------------
        # ORDER TOTAL
        # -------------------------------------------------

        order.subtotal = subtotal

        order.total_amount = (
            subtotal +
            max_shipping_charge
        )

        order.save(
            update_fields=[
                "subtotal",
                "total_amount",
                "shipping_charges"
            ]
        )

        # -------------------------------------------------
        # CLEAR CHECKOUT SESSION
        # -------------------------------------------------

        request.session.pop(
            "checkout_items",
            None
        )

        request.session.modified = True

        return order




from rest_framework import serializers
from .models import Order, OrderItem

class OrderItemSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.name")
    product_image = serializers.SerializerMethodField()

    class Meta:
        model = OrderItem
        fields = ["id", "product_name", "product_image", "quantity", "price"]

    def get_product_image(self, obj):
        image = obj.product.images.first()
        return image.image.url if image else None


# class OrderRequestSerializer(serializers.ModelSerializer):
#     class Meta:
#         model = OrderRequest
#         fields = ["request_type", "comment", "status", "created_at"]


# class OrderDetailSerializer(serializers.ModelSerializer):
#     items = OrderItemSerializer(many=True)
#     # requests = OrderRequestSerializer(many=True)

#     class Meta:
#         model = Order
#         fields = [
#             "id",
#             "order_number",
#             "status",
#             "created_at",
#             "subtotal",
#             "discount",
#             "total_amount",
#             "shipping_method",
#             "tracking_number",
#             "shipping_address",
#             "estimated_delivery",
#             "customer_name",
#             "customer_email",
#             "customer_phone",
#             "items",
#         ]
from .models import OrderRequest, OrderItem

class OrderRequestSerializer(serializers.ModelSerializer):
    items = serializers.StringRelatedField(many=True)  # or use PrimaryKeyRelatedField if needed

    class Meta:
        model = OrderRequest
        fields = [
            "id",
            "request_type",
            "items",
            "reason",
            "preferred_action",
            "status",
            "created_at",
        ]
class OrderDetailSerializer(serializers.ModelSerializer):
    customer_name = serializers.SerializerMethodField()
    customer_email = serializers.SerializerMethodField()
    customer_phone = serializers.SerializerMethodField()
    shipping_address_text = serializers.SerializerMethodField()
    billing_address_text = serializers.SerializerMethodField()
    items = OrderItemSerializer(many=True, read_only=True)
    requests = OrderRequestSerializer(many=True, read_only=True)  # NEW

    class Meta:
        model = Order
        fields = [
            "id",
            "order_number",
            "placed_at",
            "total_amount",
            "shipping_charges",
            "payment_method",
            "payment_status",
            "status",
            "transaction_id",
            "notes",
            "customer_name",
            "customer_email",
            "customer_phone",
            "shipping_address_text",
            "billing_address_text",
            "items",
            "qr_code",
            "requests",
        ]

    def get_customer_name(self, obj):
        if obj.shipping_address:
            return obj.shipping_address.full_name
        if obj.user:
            return getattr(obj.user, "email", "Guest")
        return "Guest"

    def get_customer_email(self, obj):
        return getattr(obj.user, "email", "")

    def get_customer_phone(self, obj):
        if obj.shipping_address:
            return obj.shipping_address.phone
        return ""

    def get_shipping_address_text(self, obj):
        if not obj.shipping_address:
            return ""
        addr = obj.shipping_address
        return f"{addr.street_address}, {addr.city}, {addr.state}, {addr.country}, {addr.postal_code}"

    def get_billing_address_text(self, obj):
        if not obj.billing_address:
            return ""
        addr = obj.billing_address
        return f"{addr.street_address}, {addr.city}, {addr.state}, {addr.country}, {addr.postal_code}"
        
class OrderRequestSerializer(serializers.ModelSerializer):
    items = serializers.PrimaryKeyRelatedField(
        queryset=OrderItem.objects.all(),
        many=True,
        required=False,
        allow_null=True
    )

    class Meta:
        model = OrderRequest
        fields = [
            "id",
            "order",
            "user",
            "request_type",
            "items",
            "reason",
            "preferred_action",
            "attachment",
            "status",
            "created_at",
        ]
        read_only_fields = ["id", "user", "status", "created_at"]

    def create(self, validated_data):
        # Pop items if provided; default to empty list
        items_data = validated_data.pop("items", [])

        # Set the user from context (request.user)
        user = self.context["request"].user
        validated_data["user"] = user

        # Create the order request
        order_request = OrderRequest.objects.create(**validated_data)

        # Handle items
        if not items_data:
            # If no items selected, attach all items of the order
            order_request.items.set(validated_data["order"].items.all())
        else:
            # Only attach valid items
            order_request.items.set(items_data)

        return order_request


from rest_framework import serializers
from .models import OrderItem
from products.models import ProductReview


class ProductReviewSerializer(serializers.ModelSerializer):

    class Meta:
        model = ProductReview
        fields = ["id", "product", "rating", "comment"]

    def validate(self, attrs):
        user = self.context["request"].user
        product = attrs["product"]
        # Check if user bought this product and order shipped
       
        has_bought = OrderItem.objects.filter(
            order__user=user,
            order__status="delivered",
            product=product
        ).exists()

        if not has_bought:
            raise serializers.ValidationError(
                "You can review only purchased & shipped products."
            )

        # Prevent duplicate review
        if ProductReview.objects.filter(user=user, product=product).exists():
            raise serializers.ValidationError(
                "You already reviewed this product."
            )

        return attrs

# serializers.py

from .models import Notification


class NotificationSerializer(serializers.ModelSerializer):

    class Meta:
        model = Notification
        fields = [
            'id',
            'title',
            'message',
            'notification_type',
            # 'is_read',
            'created_at'
        ]