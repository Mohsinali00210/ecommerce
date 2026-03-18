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
        fields = ['id', 'product', 'option_name', 'option']

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
            'price','compare_at', 'compare_at_price', 'discount_percentage', 'bulk_discount_rules',
            'weight', 'length', 'width', 'height', 'shipping_class', 
            'free_shipping', 'handling_time', 'meta_title', 'meta_description', 
            'slug', 'focus_keywords', 'tags', 'stock_status','stock_quantity','status', 'variants', 
            'images', 'reviews', 'promotions', 'is_active','options','video', 'available_start_date',
            'available_end_date','allow_customer_reviews','customer_can_see_stock','product_type', 
            'mark_as_new','available_for_preorder','admin_comment','disable_buy_button',
            'disable_wishlist_button','tax_category','tax_exempt','old_price','original_price',
            'other_product_cost','shipping_enabled','ship_separately','shipping_charges',
            'additional_shipping_charges','qoute'

        ]
        read_only_fields = [ 'created_at', 'modified_at']
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
        variant_images = request.FILES.getlist("variants[]")

        if raw_variants:
            try:
                variants_data = json.loads(raw_variants)
            except json.JSONDecodeError:
                raise serializers.ValidationError(
                    {"variants": "Invalid JSON format."}
                )

            for index, variant_data in enumerate(variants_data):

                variant = ProductVariant.objects.create(
                    product=product,
                    **variant_data
                )

                # Attach variant image if available
                if index < len(variant_images):
                    product_image = ProductImage.objects.create(
                        product=product,
                        image=variant_images[index]
                    )
                    variant.image = product_image
                    variant.save()

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

                for value in option_values:
                    ProductVariantOption.objects.create(
                        product=product,
                        option_name=option_name,
                        option=value
                    )

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
# class ProductSerializer(serializers.ModelSerializer):
#     # Nested Relationships
    
    
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
#             'price','compare_at', 'compare_at_price', 'discount_percentage', 'bulk_discount_rules',
#             'weight', 'length', 'width', 'height', 'shipping_class', 
#             'free_shipping', 'handling_time', 'meta_title', 'meta_description', 
#             'slug', 'focus_keywords', 'tags', 'stock_status','stock_quantity','status', 'variants', 
#             'images', 'reviews', 'promotions', 'is_active','options','video', 'available_start_date',
#             'available_end_date','allow_customer_reviews','product_type', 
#             'mark_as_new','available_for_preorder','admin_comment','disable_buy_button',
#             'disable_wishlist_button','tax_category','tax_exempt','old_price','original_price',
#             'other_product_cost','shipping_enabled','ship_separately','shipping_charges',
#             'additional_shipping_charges','qoute'

#         ]
#         read_only_fields = [ 'created_at', 'modified_at']
#     @transaction.atomic
#     def create(self, validated_data):
        

#         tags_data = validated_data.pop('tags', []) 
        
#         # variants_data = validated_data.pop('variants', [])
#         # images_data = validated_data.pop('images', [])
#         # promotion = validated_data.pop('promotions', [])
#         request = self.context.get('request')
#         variant_imgs = request.FILES.getlist('variants[]')  # adjust name if needed
#         raw_variants = request.data.getlist('variants')
#         print("raw_variants ", raw_variants)
#         print("variant_imgs ", variant_imgs)
#         return
#         try:
#             variants_data = json.loads(raw_variants[0])
#         except json.JSONDecodeError:
#             raise serializers.ValidationError({"variants": "Invalid JSON format."})
#         variant_imgs = []
#         for variant_data in variants_data:
#             image_file = variant_data.pop('image', None)
#             variant_imgs.append(image_file)
#         serializer = ProductVariantSerializer(data=variants_data, many=True)

#         raw_options = request.data.getlist('options')
#         try:
#             options_data = json.loads(raw_options[0])
#         except json.JSONDecodeError:
#             raise serializers.ValidationError({"options": "Invalid JSON format."})
#         options = ProductVariantOptionSerializer(data=options_data, many=True)

#         images_data = request.data.getlist('images')
#         if images_data:
#             images = ProductImageSerializer(data=images_data, many=True, required=False)


#         raw_promotion = request.data.getlist('promotions')
#         try:
#             promotion = json.loads(raw_promotion[0])
#         except json.JSONDecodeError:
#             raise serializers.ValidationError({"variants": "Invalid JSON format."})
#         if promotion:
#             # promotions = PromotionSerializer(data=promotion, many=True, read_only=True)
#             promo_serializer = PromotionSerializer(data=promotion[0])

#         serializer.is_valid(raise_exception=True)  
#         validated_variants = serializer.validated_data

        
#         category = validated_data.pop('category', [])
#         # brand = validated_data.pop('brand', [])
#         # tax_category = validated_data.pop('tax_category', [])
#         # taxgate_ins=TaxCategory.objects.filter(id=tax_category)
#         # brand_ins=Brand.objects.filter(id=brand)
#         product = Product.objects.create(**validated_data)
#         # product.brand=brand
#         # product.tax_category=tax_category
#         if category is not None:
#             product.category.set(category)
        
#         if promotion:            
#             if promo_serializer.is_valid(raise_exception=True):
#                 promo_ins = Promotion.objects.create(**promo_serializer.validated_data)
#                 promo_ins.products.set([product])
                
#                 if category:
#                     promo_ins.categories.set(category)
#         print(images_data)
#         product_images = []
#         for image_file in images_data:
#             product_images.append(
#                 ProductImage.objects.create(
#                     product=product,
#                     image=image_file
#                 )
#             )
#         tags_list = self.context['request'].data.getlist('tags_list')
#         for tag_name in tags_list:
#             tag_obj, _ = Tag.objects.get_or_create(name=tag_name.strip())
#             product.tags.add(tag_obj)

#         if raw_variants:
#             variants_data = json.loads(raw_variants[0])  # decode JSON
#             for i, variant_data in enumerate(variants_data):
#                 # Remove image from JSON if accidentally included
#                 image_file = variant_data.pop('image', None)

#                 # Create ProductVariant
#                 variant = ProductVariant.objects.create(
#                     product=product,
#                     **variant_data
#                 )

#                 # Attach image if available
#                 try:
#                     img_file = variant_imgs[i]
#                 except IndexError:
#                     img_file = None

#                 if img_file:
#                     # Create ProductImage linked to the product
#                     product_image = ProductImage.objects.create(
#                         product=product,
#                         image=img_file
#                     )
#                     # Assign image to variant
#                     variant.image = product_image
#                     variant.save()
#         if options_data:
#             for item in options_data:
#                 option_name = item.get('option_name')
#                 option_values = item.get('option')
#                 for val in option_values:
#                     ProductVariantOption.objects.create( product=product, option=val, option_name=option_name)
                    
#         return product





# class ProductSerializer(serializers.ModelSerializer):
#     # Define these as SerializerMethods or write-only fields to avoid class-level logic errors
#     reviews = ProductReviewSerializer(many=True, read_only=True)
    
#     # We define these as 'required=False' because we handle them manually in create()
#     variants = serializers.JSONField(write_only=True, required=False)
#     images = serializers.ListField(
#         child=serializers.ImageField(), write_only=True, required=False
#     )
#     promotions = serializers.JSONField(write_only=True, required=False)

#     category = serializers.PrimaryKeyRelatedField(
#         many=True, 
#         queryset=Category.objects.all()
#     )
#     brand = serializers.PrimaryKeyRelatedField(
#         queryset=Brand.objects.all(),
#         required=False,
#         allow_null=True
#     )
#     category_name = serializers.ReadOnlyField(source='category.name')

#     class Meta:
#         model = Product
#         fields = [
#             'id', 'name', 'sku', 'category', 'brand', 'category_name', 'description', 
#             'brief_description', 'price', 'compare_at_price', 'discount_percentage', 
#             'bulk_discount_rules', 'weight', 'length', 'width', 'height', 
#             'shipping_class', 'free_shipping', 'handling_time', 'meta_title', 
#             'meta_description', 'slug', 'focus_keywords', 'tags', 'status', 
#             'variants', 'images', 'reviews', 'promotions', 'is_active'
#         ]
#         read_only_fields = ['created_at', 'modified_at']

#     @transaction.atomic
#     def create(self, validated_data):
#         # 1. Extract data
#         request = self.context.get('request')
#         categories = validated_data.pop('category', [])
#         brand = validated_data.pop('brand', [])
#         # Tags are usually sent as a list of strings in multipart
#         # tags_list = request.data.getlist('tags_list') 
        
#         # 2. Create the main Product
#         product = Product.objects.create(**validated_data)
        
#         # 3. Set Many-to-Many Relationships
#         if categories:
#             product.category.set(categories)

#         # for tag_name in tags_list:
#         #     tag_obj, _ = Tag.objects.get_or_create(name=tag_name.strip())
#         #     product.tags.set(tag_obj)
#         # tags_list = self.context['request'].data.getlist('tags_list')
#         # for tag_name in tags_list:
#         #     tag_obj, _ = Tag.objects.get_or_create(name=tag_name.strip())
#         #     product.tags.add(tag_obj)
#         # 4. Handle Product Images (Files)
#         # images_data = request.FILES.getlist('images')
#         # for image_file in images_data:
#         #     ProductImage.objects.create(product=product, image=image_file)

#         # 5. Handle Variants (JSON string from Form-Data)
#         # raw_variants = request.data.get('variants')
#         # if raw_variants:
#         #     try:
#         #         # If sent via FormData, it might be a JSON string
#         #         variants_data = json.loads(raw_variants) if isinstance(raw_variants, str) else raw_variants
                
#         #         # Validate the nested data using the variant serializer
#         #         variant_serializer = ProductVariantSerializer(data=variants_data, many=True)
#         #         variant_serializer.is_valid(raise_exception=True)
                
#         #         for v_data in variant_serializer.validated_data:
#         #             ProductVariant.objects.create(product=product, **v_data)
#         #     except (json.JSONDecodeError, TypeError):
#         #         raise serializers.ValidationError({"variants": "Invalid JSON format."})

#         # 6. Handle Promotions
#         # raw_promotions = request.data.get('promotions')
#         # if raw_promotions:
#         #     try:
#         #         promo_data = json.loads(raw_promotions) if isinstance(raw_promotions, str) else raw_promotions
#         #         # Logic for linking promotions depends on your model structure
#         #         # Example:
#         #         for p in promo_data:
#         #            promo_obj = Promotion.objects.get(id=p['id'])
#         #            product.promotions.add(promo_obj)
#         #     except Exception as e:
#         #         print(f"Promotion error: {e}")

#         return product


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