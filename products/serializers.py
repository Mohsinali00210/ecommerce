from rest_framework import serializers
from .models import TaxCategory,ProductVariantOption, ProductAttribute,Tag, Category, Attribute_Types,Brand, Product, ProductVariant, ProductImage, ProductReview, Promotion
import pdb
import json
from django.db import transaction

class CategorySerializer(serializers.ModelSerializer):
    created_by_name = serializers.ReadOnlyField(source='created_by.full_name')

    class Meta:
        model = Category
        fields = [
            'id', 'name',  'is_active', 'parent',
            'is_deleted', 'created_at', 'created_by', 'created_by_name'
        ]
        read_only_fields = ['created_by', 'created_at']

class ProductAttributeSerializer(serializers.ModelSerializer):
    # These provide read-only context for the UI
    category_names = serializers.StringRelatedField(source='categories', many=True, read_only=True)
    attribute_type_name = serializers.ReadOnlyField(source='attribute_type.input_type')
    categories = serializers.PrimaryKeyRelatedField(
        many=True, 
        queryset=Category.objects.all()
    )
    def create(self, validated_data):
        categories = validated_data.pop('categories', [])
        instance = ProductAttribute.objects.create(**validated_data)
        if categories:
            instance.categories.set(categories)
            
        return instance

    def update(self, instance, validated_data):
        categories = validated_data.pop('categories', None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        if categories is not None:
            instance.categories.set(categories)
            
        return instance
    class Meta:
        model = ProductAttribute
        fields = [
            'id', 'name', 'categories', 'category_names', 'attribute_type', 
            'attribute_type_name', 'is_required', 'is_multiple', 
            'is_active', 'created_at', 'modified_at', 'created_by', 'modified_by'
        ]
        read_only_fields = ['created_by', 'modified_by', 'created_at', 'modified_at']


class AttributeTypesSerializer(serializers.ModelSerializer):
\
    class Meta:
        model = Attribute_Types
        fields = [
            'id', 'input_type',  'is_active', 
        ]
        read_only_fields = ['is_active']

class BrandSerializer(serializers.ModelSerializer):
    category_names = serializers.StringRelatedField(source='categories', many=True, read_only=True)
    categories = serializers.PrimaryKeyRelatedField(
        many=True, 
        queryset=Category.objects.all()
    )
    def create(self, validated_data):
        categories = validated_data.pop('categories', [])
        instance = Brand.objects.create(**validated_data)
        if categories:
            instance.categories.set(categories)
            
        return instance

    def update(self, instance, validated_data):
        categories = validated_data.pop('categories', None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        if categories is not None:
            instance.categories.set(categories)
            
        return instance
    class Meta:
        model = Brand
        fields = [
            'id', 'name', 'logo', 'website', 'categories', 'category_names',
            'is_active', 'created_at', 'modified_at', 'created_by', 'modified_by'
        ]
        read_only_fields = ['created_by', 'modified_by']





class ProductImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductImage
        fields = ['id', 'image', 'is_primary', 'alt_text']

class ProductVariantOptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductVariantOption
        fields = ['id', 'product', 'option_name', 'option','is_custom_ui','value']

class ProductVariantSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductVariant
        fields = ['id', 'name', 'sku', 'price', 'stock_quantity', 'image']

class ProductReviewSerializer(serializers.ModelSerializer):
    user_name = serializers.ReadOnlyField(source='user.username')

    class Meta:
        model = ProductReview
        fields = ['id', 'user', 'user_name', 'rating', 'comment', 'created_at']

class PromotionSerializer(serializers.ModelSerializer):
    is_running = serializers.BooleanField(source='is_currently_running', read_only=True)

    class Meta:
        model = Promotion
        fields = [
            'id', 'name', 'promo_code', 'discount_type', 'compare_at','compare_at_price','discounted_price',
            'discount_value', 'start_date', 'end_date', 'is_running'
        ]


# Changes vs. your current ProductSerializer.create()/update():
#
# Every nested block (images, tags, variants, options, promotions) now
# runs inside its own try/except. On failure it:
#   1. Writes an ErrorLog row naming the exact table + field that broke
#      (e.g. table="ProductVariant", field="variants[2].sku").
#   2. Raises serializers.ValidationError({"variants": "..."}) so the
#      response is a normal 400 with that field name as the key — which
#      the frontend's highlightServerErrors() already knows how to point
#      at the right input.
#
# This means one bad variant no longer produces a bare, unlabeled 500 —
# you get "variants[2].sku: SKU already exists" back, logged, and
# highlighted on screen.

# import json
# from django.db import transaction, IntegrityError
# from rest_framework import serializers

# from accounts.models import ErrorLog  # adjust import path as needed
# from .error_logging_mixin import extract_field_from_integrity_error  # adjust import path as needed


# def _log_and_raise(request, table_name, field_name, exc):
#     ErrorLog.objects.create(
#         level='validation',
#         field_name=field_name,
#         table_name=table_name,
#         view_name='ProductSerializer',
#         message=str(exc),
#         user=request.user if request and request.user and request.user.is_authenticated else None,
#     )
#     raise serializers.ValidationError({field_name: str(exc)})


# class ProductSerializer(serializers.ModelSerializer):
    
    
#     reviews = ProductReviewSerializer(many=True, read_only=True)
#     variants = ProductVariantSerializer(many=True, read_only=True)
#     promotions = PromotionSerializer(many=True, read_only=True)
#     images = ProductImageSerializer(many=True, read_only=True)
#     options = ProductVariantOptionSerializer(many=True, read_only=True)
    

#     category = serializers.PrimaryKeyRelatedField( many=True, queryset=Category.objects.all())
#     brand = serializers.PrimaryKeyRelatedField( queryset=Brand.objects.all(), required=False, allow_null=True )
#     tax_category = serializers.PrimaryKeyRelatedField( queryset=TaxCategory.objects.all(), required=False, allow_null=True )
#     # Read-only convenience fields
#     category_name = serializers.ReadOnlyField(source='category.name')

#     class Meta:
#         model = Product
#         fields = [
#             'id', 'name', 'sku', 'category','brand', 'category_name', 'description', 'brief_description',
#             'price','compare_at',  'bulk_discount_rules',
#             'weight', 'length', 'width', 'height', 'shipping_class', 
#             'free_shipping', 'handling_time', 'meta_title', 'meta_description', 
#             'slug', 'focus_keywords', 'tags', 'stock_status','stock_quantity','status', 'variants', 
#             'images', 'reviews', 'promotions', 'is_active','options','video', 'available_start_date',
#             'available_end_date','allow_customer_reviews','customer_can_see_stock','product_type', 
#             'mark_as_new','available_for_preorder','admin_comment','disable_buy_button',
#             'disable_wishlist_button','tax_category','tax_exempt','old_price','original_price',
#             'other_product_cost','shipping_enabled','ship_separately','shipping_charges',
#             'additional_shipping_charges','qoute' #,'is_custom_ui','value','discount_percentage',, 'compare_at_price'

#         ]
#         read_only_fields = [ 'created_at', 'modified_at']
#     @transaction.atomic
#     def update(self, instance, validated_data):
#         request = self.context.get("request")
#         categories = validated_data.pop("category", None)

#         instance = super().update(instance, validated_data)

#         if categories is not None:
#             instance.category.set(categories)

#         # ---- New images (appended, not replacing existing) ----
#         try:
#             for image in request.FILES.getlist("images"):
#                 ProductImage.objects.create(product=instance, image=image)
#         except IntegrityError as exc:
#             _log_and_raise(request, 'ProductImage', 'images', exc)

#         # ---- Tags: replace wholesale if submitted ----
#         tags_list = request.data.getlist("tags_list")
#         if tags_list:
#             try:
#                 instance.tags.clear()
#                 for tag_name in tags_list:
#                     tag_obj, _ = Tag.objects.get_or_create(name=tag_name.strip())
#                     instance.tags.add(tag_obj)
#             except IntegrityError as exc:
#                 _log_and_raise(request, 'Tag', 'tags_list', exc)

#         # ---- Variants: update existing, create new, delete removed ----
#         raw_variants = request.data.get("variants")
#         if raw_variants is not None:
#             try:
#                 variants_data = json.loads(raw_variants)
#             except json.JSONDecodeError:
#                 raise serializers.ValidationError({"variants": "Invalid JSON format."})

#             submitted_ids = []
#             for index, variant_data in enumerate(variants_data):
#                 field_key = f"variants[{index}]"
#                 variant_id = variant_data.pop("id", None)
#                 image_file = request.FILES.get(f"variants[{index}][image]")

#                 try:
#                     variant = None
#                     if variant_id:
#                         variant = ProductVariant.objects.filter(id=variant_id, product=instance).first()

#                     if variant:
#                         for attr, value in variant_data.items():
#                             setattr(variant, attr, value)
#                     else:
#                         variant = ProductVariant.objects.create(product=instance, **variant_data)

#                     if image_file:
#                         product_image = ProductImage.objects.create(product=instance, image=image_file)
#                         variant.image = product_image

#                     variant.save()
#                 except IntegrityError as exc:
#                     # e.g. duplicate SKU on this specific row — tag the
#                     # error with which variant row and which column broke.
#                     field_name = f"{field_key}.{extract_field_from_integrity_error(exc) or 'unknown'}"
#                     _log_and_raise(request, 'ProductVariant', field_name, exc)

#                 submitted_ids.append(variant.id)

#             instance.variants.exclude(id__in=submitted_ids).delete()

#         return instance

#     @transaction.atomic
#     def create(self, validated_data):
#         request = self.context.get("request")

#         categories = validated_data.pop("category", [])
#         validated_data.pop("tags", [])

#         try:
#             product = Product.objects.create(**validated_data)
#         except IntegrityError as exc:
#             field_name = extract_field_from_integrity_error(exc) or 'unknown'
#             _log_and_raise(request, 'Product', field_name, exc)

#         if categories:
#             product.category.set(categories)

#         # ---- Images ----
#         try:
#             for image in request.FILES.getlist("images"):
#                 ProductImage.objects.create(product=product, image=image)
#         except IntegrityError as exc:
#             _log_and_raise(request, 'ProductImage', 'images', exc)

#         # ---- Tags ----
#         try:
#             for tag_name in request.data.getlist("tags_list"):
#                 tag_obj, _ = Tag.objects.get_or_create(name=tag_name.strip())
#                 product.tags.add(tag_obj)
#         except IntegrityError as exc:
#             _log_and_raise(request, 'Tag', 'tags_list', exc)

#         # ---- Variants ----
#         raw_variants = request.data.get("variants")
#         if raw_variants:
#             try:
#                 variants_data = json.loads(raw_variants)
#             except json.JSONDecodeError:
#                 raise serializers.ValidationError({"variants": "Invalid JSON format."})

#             for index, variant_data in enumerate(variants_data):
#                 field_key = f"variants[{index}]"
#                 try:
#                     variant = ProductVariant.objects.create(product=product, **variant_data)
#                     image_file = request.FILES.get(f"variants[{index}][image]")
#                     if image_file:
#                         product_image = ProductImage.objects.create(product=product, image=image_file)
#                         variant.image = product_image
#                         variant.save()
#                 except IntegrityError as exc:
#                     field_name = f"{field_key}.{extract_field_from_integrity_error(exc) or 'unknown'}"
#                     _log_and_raise(request, 'ProductVariant', field_name, exc)

#         # ---- Options ----
#         raw_options = request.data.get("options")
#         if raw_options:
#             try:
#                 options_data = json.loads(raw_options)
#             except json.JSONDecodeError:
#                 raise serializers.ValidationError({"options": "Invalid JSON format."})

#             try:
#                 for item in options_data:
#                     option_name = item.get("option_name")
#                     option_values = item.get("option", [])
#                     color_values = item.get("value", [])
#                     for index, value in enumerate(option_values):
#                         color_code = None
#                         if option_name and option_name.lower() == "color" and index < len(color_values):
#                             color_code = color_values[index]
#                         ProductVariantOption.objects.create(
#                             product=product, option_name=option_name, option=value, value=color_code
#                         )
#             except IntegrityError as exc:
#                 _log_and_raise(request, 'ProductVariantOption', 'options', exc)

#         # ---- Promotion ----
#         raw_promotions = request.data.get("promotions")
#         if raw_promotions:
#             try:
#                 promotion_data = json.loads(raw_promotions)
#             except json.JSONDecodeError:
#                 raise serializers.ValidationError({"promotions": "Invalid JSON format."})

#             if promotion_data:
#                 promo_serializer = PromotionSerializer(data=promotion_data[0])
#                 promo_serializer.is_valid(raise_exception=True)  # bubbles up as a normal 400 already

#                 try:
#                     promo = Promotion.objects.create(**promo_serializer.validated_data)
#                     promo.products.set([product])
#                     if categories:
#                         promo.categories.set(categories)
#                 except IntegrityError as exc:
#                     _log_and_raise(request, 'Promotion', 'promotions', exc)

#         return product


class ProductSerializer(serializers.ModelSerializer):
    # Nested Relationships
    
    
    reviews = ProductReviewSerializer(many=True, read_only=True)
    variants = ProductVariantSerializer(many=True, read_only=True)
    promotions = PromotionSerializer(many=True, read_only=True)
    images = ProductImageSerializer(many=True, read_only=True)
    options = ProductVariantOptionSerializer(many=True, read_only=True)
    

    category = serializers.PrimaryKeyRelatedField( many=True, queryset=Category.objects.all())
    brand = serializers.PrimaryKeyRelatedField( queryset=Brand.objects.all(), required=False, allow_null=True )
    tax_category = serializers.PrimaryKeyRelatedField( queryset=TaxCategory.objects.all(), required=False, allow_null=True )
    # Read-only convenience fields
    category_name = serializers.ReadOnlyField(source='category.name')

    class Meta:
        model = Product
        fields = [
            'id', 'name', 'sku', 'category','brand', 'category_name', 'description', 'brief_description',
            'price','compare_at',  'bulk_discount_rules',
            'weight', 'length', 'width', 'height', 'shipping_class', 
            'free_shipping', 'handling_time', 'meta_title', 'meta_description', 
            'slug', 'focus_keywords', 'tags', 'stock_status','stock_quantity','status', 'variants', 
            'images', 'reviews', 'promotions', 'is_active','options','video', 'available_start_date',
            'available_end_date','allow_customer_reviews','customer_can_see_stock','product_type', 
            'mark_as_new','available_for_preorder','admin_comment','disable_buy_button',
            'disable_wishlist_button','tax_category','tax_exempt','old_price','original_price',
            'other_product_cost','shipping_enabled','ship_separately','shipping_charges',
            'additional_shipping_charges','qoute' #,'is_custom_ui','value','discount_percentage',, 'compare_at_price'

        ]
        read_only_fields = [ 'created_at', 'modified_at']
    @transaction.atomic
    def update(self, instance, validated_data):
        request = self.context.get("request")
        categories = validated_data.pop("category", None)

        instance = super().update(instance, validated_data)

        if categories is not None:
            instance.category.set(categories)

        # ---- New images (appended, not replacing existing) ----
        for image in request.FILES.getlist("images"):
            ProductImage.objects.create(product=instance, image=image)

        # ---- Tags: replace wholesale if submitted ----
        tags_list = request.data.getlist("tags_list")
        if tags_list:
            instance.tags.clear()
            for tag_name in tags_list:
                tag_obj, _ = Tag.objects.get_or_create(name=tag_name.strip())
                instance.tags.add(tag_obj)

        # ---- Variants: update existing, create new, delete removed ----
        raw_variants = request.data.get("variants")
        if raw_variants is not None:
            try:
                variants_data = json.loads(raw_variants)
            except json.JSONDecodeError:
                raise serializers.ValidationError({"variants": "Invalid JSON format."})

            submitted_ids = []
            for index, variant_data in enumerate(variants_data):
                variant_id = variant_data.pop("id", None)
                image_file = request.FILES.get(f"variants[{index}][image]")

                variant = None
                if variant_id:
                    variant = ProductVariant.objects.filter(id=variant_id, product=instance).first()

                if variant:
                    for attr, value in variant_data.items():
                        setattr(variant, attr, value)
                else:
                    variant = ProductVariant.objects.create(product=instance, **variant_data)

                if image_file:
                    product_image = ProductImage.objects.create(product=instance, image=image_file)
                    variant.image = product_image

                variant.save()
                submitted_ids.append(variant.id)

            instance.variants.exclude(id__in=submitted_ids).delete()

        # ---- Options: replace all ----
        # raw_options = request.data.get("options")
        # if raw_options is not None:
        #     try:
        #         options_data = json.loads(raw_options)
        #     except json.JSONDecodeError:
        #         raise serializers.ValidationError({"options": "Invalid JSON format."})

        #     instance.options.all().delete()
        #     for item in options_data:
        #         option_name = item.get("option_name")
        #         option_values = item.get("option", [])
        #         color_values = item.get("value", [])
        #         for idx, value in enumerate(option_values):
        #             color_code = None
        #             if option_name and option_name.lower() == "color" and idx < len(color_values):
        #                 color_code = color_values[idx]
        #             ProductVariantOption.objects.create(
        #                 product=instance, option_name=option_name, option=value, value=color_code
        #             )

        # ---- Promotion: update the existing one, or create ----
        # raw_promotions = request.data.get("promotions")
        # if raw_promotions is not None:
        #     try:
        #         promotion_data = json.loads(raw_promotions)
        #     except json.JSONDecodeError:
        #         raise serializers.ValidationError({"promotions": "Invalid JSON format."})

        #     if promotion_data:
        #         existing_promo = instance.promotions.first()
        #         promo_serializer = PromotionSerializer(instance=existing_promo, data=promotion_data[0])
        #         promo_serializer.is_valid(raise_exception=True)
        #         promo = promo_serializer.save()
        #         promo.products.set([instance])
        #         if categories:
        #             promo.categories.set(categories)

        return instance
    @transaction.atomic
    def create(self, validated_data):

        request = self.context.get("request")

        # ----------------------------
        # Extract ManyToMany / Special Fields
        # ----------------------------
        categories = validated_data.pop("category", [])
        tags_data = validated_data.pop("tags", [])

        # ----------------------------
        # Create Product
        # ----------------------------
        product = Product.objects.create(**validated_data)

        if categories:
            product.category.set(categories)

        # ----------------------------
        # Handle Product Images
        # ----------------------------
        product_images = request.FILES.getlist("images")

        for image in product_images:
            ProductImage.objects.create(
                product=product,
                image=image
            )

        # ----------------------------
        # Handle Tags
        # ----------------------------
        tags_list = request.data.getlist("tags_list")

        for tag_name in tags_list:
            tag_obj, _ = Tag.objects.get_or_create(name=tag_name.strip())
            product.tags.add(tag_obj)

        # ----------------------------
        # Handle Variants
        # ----------------------------
        raw_variants = request.data.get("variants")
        #variant_images = request.FILES.getlist("variants[]")

        if raw_variants:
            try:
                variants_data = json.loads(raw_variants)
            except json.JSONDecodeError:
                raise serializers.ValidationError(
                    {"variants": "Invalid JSON format."}
                )
            for index, variant_data in enumerate(variants_data):
                variant = ProductVariant.objects.create(product=product, **variant_data)

                image_file = request.FILES.get(f"variants[{index}][image]")
                if image_file:
                    product_image = ProductImage.objects.create(product=product, image=image_file)
                    variant.image = product_image
                    variant.save()
            # for index, variant_data in enumerate(variants_data):

            #     variant = ProductVariant.objects.create(
            #         product=product,
            #         **variant_data
            #     )

            #     # Attach variant image if available
            #     if index < len(variant_images):
            #         product_image = ProductImage.objects.create(
            #             product=product,
            #             image=variant_images[index]
            #         )
            #         variant.image = product_image
            #         variant.save()

        # ----------------------------
        # Handle Options
        # ----------------------------
        raw_options = request.data.get("options")

        if raw_options:
            try:
                options_data = json.loads(raw_options)
            except json.JSONDecodeError:
                raise serializers.ValidationError(
                    {"options": "Invalid JSON format."}
                )

            for item in options_data:
                option_name = item.get("option_name")
                option_values = item.get("option", [])

                color_values = item.get("value", [])
                for index, value in enumerate(option_values):
                    color_code = None
                    if option_name.lower() == "color" and index < len(color_values):
                        color_code = color_values[index]
                    ProductVariantOption.objects.create(
                        product=product,
                        option_name=option_name,
                        option=value,
                        value=color_code
                    )
                # for value in option_values:
                #     ProductVariantOption.objects.create(
                #         product=product,
                #         option_name=option_name,
                #         option=value,
                #         value=
                #     )

        # ----------------------------
        # Handle Promotion
        # ----------------------------
        raw_promotions = request.data.get("promotions")

        if raw_promotions:
            try:
                promotion_data = json.loads(raw_promotions)
            except json.JSONDecodeError:
                raise serializers.ValidationError(
                    {"promotions": "Invalid JSON format."}
                )

            if promotion_data:
                promo_serializer = PromotionSerializer(
                    data=promotion_data[0]
                )
                promo_serializer.is_valid(raise_exception=True)

                promo = Promotion.objects.create(
                    **promo_serializer.validated_data
                )

                promo.products.set([product])

                if categories:
                    promo.categories.set(categories)

        return product


from .models import ProductVariantInventory,ProductVariant

class ProductVariantInventorySerializer(serializers.ModelSerializer):

    variant_name = serializers.CharField(source='variant.name', read_only=True)
    product_name = serializers.CharField(source='variant.product.name', read_only=True)

    class Meta:
        model = ProductVariantInventory
        fields = "__all__"


class ProductVariant2Serializer(serializers.ModelSerializer):

    product_name = serializers.CharField(source='product.name', read_only=True)

    class Meta:
        model = ProductVariant
        fields = [
            'id',
            'product',
            'product_name',
            'name',
            'sku',
            'price',
            'stock_quantity'
        ]


# serializers.py
from Web.models import Order,OrderRequest,OrderRequestComment

class OrderSerializer(serializers.ModelSerializer):
    order_number = serializers.SerializerMethodField()
    customer_name = serializers.SerializerMethodField()
    date = serializers.SerializerMethodField()
    total = serializers.SerializerMethodField()
    is_seen = serializers.BooleanField(read_only=True)

    class Meta:
        model = Order
        fields = [
            "id",
            "order_number",
            "customer_name",
            "date",
            "payment_method",
            "total",
            "status",
            "payment_status",
            "is_seen",
        ]

    def get_order_number(self, obj):
        return f"ORD-{obj.id}"
    def get_customer_name(self, obj):
        if not obj.user:
            return "Guest"
        
        # Try these fields in order
        for attr in ["full_name", "name", "email"]:
            value = getattr(obj.user, attr, None)
            if value:
                return value
        
        # If nothing exists, fallback
        return "Guest"

    def get_date(self, obj):
        return obj.created_at.strftime("%d %b %Y")

    def get_total(self, obj):
        # If your Order model does not have a total field, calculate it
        if hasattr(obj, "total"):  
            return float(obj.total)
        return float(sum(item.price * item.quantity for item in obj.items.all()))



from Web.models import Order, OrderItem


class OrderItemSerializer(serializers.ModelSerializer):
    product_name = serializers.SerializerMethodField()
    variant_name = serializers.SerializerMethodField()

    class Meta:
        model = OrderItem
        fields = [
            "id",
            "product_name",
            "variant_name",
            "price",
            "quantity",
            "total",
        ]

    def get_product_name(self, obj):
        return obj.product.name if obj.product else "Deleted Product"

    def get_variant_name(self, obj):
        return obj.variant.name if obj.variant else None

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
    requests = OrderRequestSerializer(many=True, read_only=True)

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

class OrderRequestCommentSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source="user.email", read_only=True)

    class Meta:
        model = OrderRequestComment
        fields = ["id", "status", "comment", "user_name", "created_at"]
class AdminOrderRequestUpdateSerializer(serializers.ModelSerializer):
    comments = OrderRequestCommentSerializer(many=True, read_only=True)
    class Meta:
        model = OrderRequest
        fields = ["status", "comments"]

class AdminProductReviewSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.name", read_only=True)
    user_email = serializers.CharField(source="user.email", read_only=True)

    class Meta:
        model = ProductReview
        fields = [
            "id",
            "product_name",
            "user_email",
            "rating",
            "comment",
            # "status",
            "is_active",
        ]


class PromotionsSerializer(serializers.ModelSerializer):
    products = serializers.PrimaryKeyRelatedField(
        many=True,
        queryset=Product.objects.all(),
        required=False
    )
    categories = serializers.PrimaryKeyRelatedField(
        many=True,
        queryset=Category.objects.all(),
        required=False
    )

    class Meta:
        model = Promotion
        fields = "__all__"


from .models import Picture
class PictureSerializer(serializers.ModelSerializer):
    picture = serializers.ImageField(required=False)
    class Meta:
        model = Picture
        fields = "__all__"