from django.db import models
from django.conf import settings
from django.utils.text import slugify
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.utils import timezone

# class Category(models.Model):
#     name = models.CharField(max_length=100, unique=True)
#     is_active = models.BooleanField(default=True)
#     is_deleted = models.BooleanField(default=False)
    
#     created_at = models.DateTimeField(auto_now_add=True)
#     created_by = models.ForeignKey(
#         settings.AUTH_USER_MODEL, 
#         on_delete=models.SET_NULL, 
#         null=True, 
#         related_name='categories'
#     )

#     def __str__(self):
#         return self.name

#     class Meta:
#         verbose_name_plural = "Categories"
class Category(models.Model):
    name = models.CharField(max_length=100)
    parent = models.ForeignKey(
        'Category',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='children'
    )

    is_active = models.BooleanField(default=True)
    is_deleted = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='categories'
    )

    class Meta:
        verbose_name_plural = "Categories"
        unique_together = ('name', 'parent')

    def __str__(self):
        return self.name


class Attribute_Types(models.Model):
    input_type = models.CharField(max_length=100, help_text="e.g., dropdown, file, text")
    
    # Configuration Flags
    is_required = models.BooleanField(default=False)
    is_multiple = models.BooleanField(default=False, help_text="Can select more than one value?")
    is_active = models.BooleanField(default=True)
    is_deleted = models.BooleanField(default=False)

    # Audit Fields
    created_at = models.DateTimeField(auto_now_add=True)
    modified_at = models.DateTimeField(auto_now=True)
    
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='attributes_created'
    )
    modified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='attributes_modified'
    )

    def __str__(self):
        return f"{self.name} ({self.get_input_type_display()})"

    class Meta:
        ordering = ['-created_at']




from django.db import models
from django.conf import settings

class ProductAttribute(models.Model):
    name = models.CharField(max_length=255, help_text="e.g., RAM Size, Fabric, or Voltage")
    
    # Links to the hierarchical Category model we built earlier
    # Many-to-Many allows one attribute to belong to multiple categories
    categories = models.ManyToManyField(
        'Category', 
        related_name='attributes',
        blank=True
    )

    # Links to the Input Type (dropdown, text, etc.)
    attribute_type = models.ForeignKey(
        'Attribute_Types', 
        on_delete=models.PROTECT, 
        related_name='product_attributes'
    )

    # Configuration
    is_required = models.BooleanField(default=False)
    is_multiple = models.BooleanField(default=False, help_text="Can user select multiple values?")
    is_active = models.BooleanField(default=True)
    is_deleted = models.BooleanField(default=False)

    # Audit Trail
    created_at = models.DateTimeField(auto_now_add=True)
    modified_at = models.DateTimeField(auto_now=True)
    
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='attributes_created_by'
    )
    modified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='attributes_modified_by'
    )

    class Meta:
        verbose_name = "Product Attribute"
        verbose_name_plural = "Product Attributes"
        unique_together = ('name', 'attribute_type')

    def __str__(self):
        return f"{self.name} ({self.attribute_type.input_type})"

from django.db import models
from django.conf import settings

class Brand(models.Model):
    name = models.CharField(max_length=100, unique=True)
    # The logo field stores the file path
    logo = models.ImageField(upload_to='brands/logos/', blank=True, null=True)
    website = models.URLField(max_length=200, blank=True, null=True)
    
    categories = models.ManyToManyField(
        'Category', 
        related_name='brands',
        blank=True
    )

    is_active = models.BooleanField(default=True)
    is_deleted = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    modified_at = models.DateTimeField(auto_now=True)
    
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='brands_created'
    )
    modified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='brands_modified'
    )

    def __str__(self):
        return self.name



from django.db import models
from django.conf import settings

class ShippingMethod(models.Model):
    # Choice definitions
    SHIPPING_TYPES = [
        ('flat', 'Flat Rate'),
        ('weight', 'Weight Based'),
        ('price', 'Price Based'),
        ('free', 'Free Shipping'),
    ]

    TAX_CLASSES = [
        ('standard', 'Standard'),
        ('reduced', 'Reduced'),
        ('zero', 'Zero Rate'),
    ]
    # Main Fields
    name = models.CharField(max_length=100, unique=True)
    estimated_delivery_time = models.CharField(
        max_length=50, 
        help_text="e.g. 3-5 Business Days"
    )
    
    shipping_type = models.CharField(
        max_length=20, 
        choices=SHIPPING_TYPES, 
        default='flat'
    )
    base_cost = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        default=0.00
    )
    tax_class = models.CharField(
        max_length=50, 
        choices=TAX_CLASSES, # Updated to use choices
        default='standard'
    )
    description = models.TextField(blank=True, null=True)

    # Configuration Flags
    is_active = models.BooleanField(default=True)
    is_deleted = models.BooleanField(default=False)

    # Audit Trail
    created_at = models.DateTimeField(auto_now_add=True)
    modified_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='shipping_methods_created'
    )
    modified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='shipping_methods_modified'
    )

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Shipping Method"
        verbose_name_plural = "Shipping Methods"

    def __str__(self):
        return f"{self.name} ({self.get_shipping_type_display()})"

class ShippingZone(models.Model):
    # Basic Information
    name = models.CharField(max_length=150, unique=True, help_text="e.g. Domestic Zone")

    # Location Mapping
    country = models.CharField(max_length=100, help_text="e.g. USA, UK")
    state_region = models.CharField(max_length=100, blank=True, null=True, help_text="Optional State or Province")
    zip_codes = models.TextField(blank=True, null=True, help_text="Comma separated list of postal codes")

    # Methods Assignment
    shipping_methods = models.ManyToManyField(
        'ShippingMethod', 
        related_name='zones',
        blank=True,
        verbose_name="Shipping Methods"
    )
    shipping_providers = models.ManyToManyField(
        'ShippingProvider', 
        related_name='zones',
        blank=True,
        verbose_name="Shipping Providers"
    )

    # Status & Audit
    is_active = models.BooleanField(default=True)
    is_deleted = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    modified_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='zones_created')
    modified_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='zones_modified')

    def __str__(self):
        return self.name

class ShippingRule(models.Model):
    CONDITION_TYPES = [
        ('order_value', 'Order Value'),
        ('order_weight', 'Order Weight'),
        ('item_count', 'Item Count'),
    ]

    zone = models.ForeignKey(ShippingZone, on_delete=models.CASCADE, related_name='rules')
    shipping_method = models.ForeignKey('ShippingMethod', on_delete=models.CASCADE)
    
    condition_type = models.CharField(max_length=20, choices=CONDITION_TYPES, default='order_value')
    min_value = models.DecimalField(max_digits=12, decimal_places=2, default=0.00, help_text="Min Order Value/Weight")
    max_value = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True, help_text="Max Order Value/Weight")
    
    shipping_cost = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)

    is_active = models.BooleanField(default=True)
    is_deleted = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    modified_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='rules_created')
    modified_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='rules_modified')

    def __str__(self):
        return f"Rule for {self.shipping_method.name} in {self.zone.name}"





class ShippingProvider(models.Model):
    RATE_TYPES = [
        ('api', 'Fetch from API'),
        ('flat', 'Flat Rate'),
        ('zone', 'Zone Based'),
    ]

    # Provider Details
    name = models.CharField(max_length=100, help_text="e.g. FedEx, DHL")
    provider_code = models.CharField(max_length=50, unique=True, help_text="Unique identifier")
    
    # API Credentials
    api_key = models.CharField(max_length=255, blank=True, null=True)
    api_secret = models.CharField(max_length=255, blank=True, null=True)
    account_number = models.CharField(max_length=100, blank=True, null=True)
    api_endpoint = models.URLField(max_length=255, blank=True, null=True)

    # Shipping Services (Stored as Boolean flags)
    has_standard_delivery = models.BooleanField(default=True)
    has_express_delivery = models.BooleanField(default=False)
    has_overnight_delivery = models.BooleanField(default=False)

    # Rate Calculation Settings
    rate_type = models.CharField(max_length=10, choices=RATE_TYPES, default='api')
    markup_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=0.00, help_text="Optional markup %")
    min_charge = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)

    # Tracking & Label
    enable_tracking = models.BooleanField(default=True)
    auto_generate_label = models.BooleanField(default=False)

    # Standard Audit Fields
    is_active = models.BooleanField(default=True)
    is_deleted = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    modified_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.SET_NULL, 
        null=True, 
        related_name='providers_created'
    )
    modified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.SET_NULL, 
        null=True, 
        related_name='providers_modified'
    )

    class Meta:
        verbose_name = "Shipping Provider"
        verbose_name_plural = "Shipping Providers"
        ordering = ['name']

    def __str__(self):
        return f"{self.name} ({self.provider_code})"



class BaseAuditModel(models.Model):
    is_active = models.BooleanField(default=True)
    is_deleted = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    modified_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="%(class)s_created")
    modified_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="%(class)s_modified")

    class Meta:
        abstract = True

class TaxCategory(BaseAuditModel):
    name = models.CharField(max_length=100)
    percentage = models.DecimalField( max_digits=5,  decimal_places=2 )
    def __str__(self):
        return f"{self.name} ({self.percentage}%)"

from django.db import models


class Warehouse(BaseAuditModel):
    name = models.CharField(max_length=150)
    location = models.CharField(max_length=255, blank=True)
    def __str__(self):
        return self.name

from django.db import models


class InventorySettings(models.Model):

    INVENTORY_METHOD_CHOICES = ( ('dont_track', 'Don’t Track Inventory'), ('track', 'Track Inventory'), ('track_by_attributes', 'Track By Product Attributes'), )
    LOW_STOCK_ACTIVITY_CHOICES = ( ('nothing', 'Nothing'), ('disable_buy', 'Disable Buy Button'), ('unpublish', 'Unpublish Product'), )
    BACKORDER_CHOICES = ( ('no_backorder', 'No Backorder'), ('allow_below_0', 'Allow Qty Below 0'), ('allow_below_0_notify', 'Allow Below 0 And Notify Customer'),)

    product = models.OneToOneField( 'Product', on_delete=models.CASCADE, related_name='inventory')
    inventory_method = models.CharField( max_length=30, choices=INVENTORY_METHOD_CHOICES, default='dont_track')

    # Shared fields
    warehouse = models.ForeignKey( Warehouse, on_delete=models.SET_NULL, null=True, blank=True)
    min_cart_qty = models.PositiveIntegerField(default=1)
    max_cart_qty = models.PositiveIntegerField(null=True, blank=True)
    allowed_quantities = models.CharField( max_length=255, blank=True, help_text="Example: 1,2,5,10")
    not_returnable = models.BooleanField(default=False)
    product_availability_range = models.CharField( max_length=100, blank=True)
    # ========== METHOD: TRACK INVENTORY ==========
    stock_quantity = models.IntegerField(null=True, blank=True)
    low_stock_quantity = models.IntegerField(null=True, blank=True)
    backorders = models.CharField( max_length=30, choices=BACKORDER_CHOICES, default='no_backorder')

    multiple_warehouses = models.BooleanField(default=False)
    display_availability = models.BooleanField(default=True)
    display_stock_quantity = models.BooleanField(default=False)
    minimum_stock_qty = models.PositiveIntegerField(null=True, blank=True)
    low_stock_activity = models.CharField( max_length=20, choices=LOW_STOCK_ACTIVITY_CHOICES, default='nothing')
    notify_qty_below = models.PositiveIntegerField(null=True, blank=True)
    allow_back_in_stock_subscriptions = models.BooleanField(default=False)

    def __str__(self):
        return f"Inventory for {self.product_id} - {self.inventory_method}"


class Product(BaseAuditModel):
    def validate_video_size(value):
        filesize = value.size
        if filesize > 50 * 1024 * 1024: # 20MB limit
            raise ValidationError("Maximum video size is 50MB")
    STATUS_CHOICES = [('active', 'Active'), ('inactive', 'Inactive'), ('featured', 'Featured')]
    STOCK_STATUS_CHOICES = [('in_stock', 'In Stock'), ('low_stock', 'Low Stock'), ('out_of_stock', 'Out Of Stock')]
    
    # Details
    name = models.CharField(max_length=255,blank=True)
    sku = models.CharField(max_length=100, unique=True)
    category = models.ManyToManyField(Category, related_name="products")
    brand = models.ForeignKey('Brand', on_delete=models.SET_NULL, null=True)
    description = models.TextField(blank=True)
    brief_description = models.TextField(blank=True)
    
    # Pricing
    price = models.DecimalField(max_digits=12, decimal_places=2)
    old_price = models.DecimalField( max_digits=10, decimal_places=2, null=True, blank=True)
    original_price = models.DecimalField( max_digits=10, decimal_places=2, null=True, blank=True)
    other_product_cost = models.DecimalField( max_digits=10, decimal_places=2, null=True, blank=True)
    compare_at_price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    compare_at = models.PositiveIntegerField(default=0)
    discount_percentage = models.PositiveIntegerField(default=0)
    bulk_discount_rules = models.TextField(blank=True, help_text="JSON or text based rules")
    
    # Shipping
    
    shipping_enabled = models.BooleanField(default=True)
    ship_separately = models.BooleanField(default=False)
    shipping_charges = models.DecimalField( max_digits=10, decimal_places=2, default=0.00)
    additional_shipping_charges = models.DecimalField( max_digits=10, decimal_places=2, default=0.00)


    weight = models.DecimalField(max_digits=10, decimal_places=2, default=0) # kg
    length = models.DecimalField(max_digits=10, decimal_places=2, default=0) # cm
    width = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    height = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    shipping_class = models.CharField(max_length=50, default='standard')
    free_shipping = models.BooleanField(default=False)
    handling_time = models.IntegerField(default=1)
    
    # SEO
    meta_title = models.CharField(max_length=255, blank=True)
    meta_description = models.TextField(blank=True)
    slug = models.SlugField(max_length=255, unique=True, blank=True)
    focus_keywords = models.CharField(max_length=255, blank=True)
    
    tags = models.ManyToManyField('Tag', blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    stock_status = models.CharField(max_length=20, choices=STOCK_STATUS_CHOICES, default='in_stock')
    stock_quantity = models.PositiveIntegerField(default=0)
    video = models.FileField(upload_to='products/videos/', validators=[validate_video_size], null=True, blank=True)

    show_on_home_page = models.BooleanField(default=False)
    display_order = models.PositiveIntegerField(default=0)
    visible_individually = models.BooleanField(default=True)

    # Product type
    PRODUCT_TYPE_CHOICES = (
        ('1', 'Simple'),
        ('2', 'Grouped'),
    )
    product_type = models.CharField( max_length=20, choices=PRODUCT_TYPE_CHOICES, default='simple')
    available_start_date = models.DateField(null=True, blank=True)
    available_end_date = models.DateField(null=True, blank=True)
    allow_customer_reviews = models.BooleanField(default=True)
    mark_as_new = models.BooleanField(default=False)
    available_for_preorder = models.BooleanField(default=False)
    disable_buy_button = models.BooleanField(default=False)
    disable_wishlist_button = models.BooleanField(default=False)
    admin_comment = models.TextField(blank=True)

    tax_exempt = models.BooleanField(default=False)
    tax_category = models.ForeignKey( TaxCategory, on_delete=models.SET_NULL, null=True, blank=True)
    
    sold = models.PositiveIntegerField(default=0)
    rating_count = models.PositiveIntegerField(default=0)
    star_count = models.PositiveIntegerField(default=0)

    qoute = models.CharField( max_length=200, null=True, blank=True)

    def get_price_for_promotion(self, promotion):
        return promotion.get_discounted_price(self.price)
    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

class ProductVariant(BaseAuditModel):
    product = models.ForeignKey(Product, related_name='variants', on_delete=models.CASCADE)
    name = models.CharField(max_length=255, help_text="e.g., Color: Red, Size: XL")
    sku = models.CharField(max_length=100, unique=True)
    price = models.DecimalField(max_digits=12, decimal_places=2)
    stock_quantity = models.PositiveIntegerField(default=0)
    # Variant can have a specific image assigned
    image = models.ForeignKey('ProductImage',related_name="variant_image", on_delete=models.CASCADE, null=True, blank=True)

class ProductVariantOption(BaseAuditModel):
    product = models.ForeignKey( Product, on_delete=models.CASCADE, related_name="variant_options")
    option_name = models.CharField( max_length=100, help_text="e.g. Color, Size" )
    option = models.CharField( max_length=100, help_text="Comma separated values e.g. Red,Blue,Green" )

    def get_options_list(self):
        return [opt.strip() for opt in self.option.split(",") if opt.strip()]

    def __str__(self):
        return f"{self.option_name} - {self.product.name}"

class ProductImage(BaseAuditModel):
    product = models.ForeignKey(Product, related_name='images', on_delete=models.CASCADE, null=True)
    image = models.ImageField(upload_to='products/%Y/%m/')
    is_primary = models.BooleanField(default=False)
    alt_text = models.CharField(max_length=255, blank=True)

class ProductReview(BaseAuditModel):
    product = models.ForeignKey(Product, related_name='reviews', on_delete=models.CASCADE)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    rating = models.PositiveIntegerField(choices=[(i, str(i)) for i in range(1, 6)])
    comment = models.TextField()



class Promotion(BaseAuditModel):
    DISCOUNT_TYPES = [
        ('percentage', 'Percentage (%)'),
        ('fixed', 'Fixed Amount'),
        ('buy_x_get_y', 'Buy X Get Y'),
        ('free_delivery', 'Free Delivery'),
    ]

    # Basic Info
    name = models.CharField(max_length=255, help_text="e.g. Summer Sale 2026")
    description = models.TextField(blank=True, null=True)
    promo_code = models.CharField(max_length=50, unique=True, blank=True, null=True)
    
    # Discount Logic
    discount_type = models.CharField(max_length=20, choices=DISCOUNT_TYPES, default='percentage')
    discount_value = models.DecimalField(blank=True,null=True,max_digits=10, decimal_places=2, help_text="Enter percentage or flat amount")
    compare_at_price = models.PositiveIntegerField(blank=True,null=True,help_text="Enter compare at price")
    discounted_price = models.PositiveIntegerField(blank=True,null=True,help_text="Enter discounted price")
    compare_at = models.PositiveIntegerField(default=0)

    # Scheduling
    start_date = models.DateTimeField()
    end_date = models.DateTimeField()

    products = models.ManyToManyField('Product', related_name='promotions', blank=True)
    categories = models.ManyToManyField('Category', related_name='promotions', blank=True)

    # Standard Audit Fields
    # is_active = models.BooleanField(default=True)
    # is_deleted = models.BooleanField(default=False)
    # created_at = models.DateTimeField(auto_now_add=True)
    # modified_at = models.DateTimeField(auto_now=True)
    # created_by = models.ForeignKey(
    #     settings.AUTH_USER_MODEL, 
    #     on_delete=models.SET_NULL, 
    #     null=True, 
    #     related_name='promotions_created'
    # )
    # modified_by = models.ForeignKey(
    #     settings.AUTH_USER_MODEL, 
    #     on_delete=models.SET_NULL, 
    #     null=True, 
    #     related_name='promotions_modified'
    # )

    class Meta:
        ordering = ['-start_date']

    def __str__(self):
        return self.name

    def get_discounted_price(self, price):
        now = timezone.now()

        if self.end_date < now:
            return price

        if self.discount_type == 'percentage' and self.discount_value:
            return price - (price * self.discount_value / 100)

        if self.discount_type == 'fixed' and self.discount_value:
            return  self.discounted_price

        return price
    @property
    def is_currently_running(self):
        now = timezone.now()
        return self.is_active and self.start_date <= now <= self.end_date

# Add this before your Product model
class Tag(BaseAuditModel):
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=100, unique=True, blank=True)

    def save(self, *args, **kwargs):
        if not self.slug:
            from django.utils.text import slugify
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name

from accounts.models import User

class Wishlist(BaseAuditModel):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="wishlists")
    product = models.ForeignKey("Product", on_delete=models.CASCADE, related_name="wishlisted_by")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("user", "product")  # Prevent duplicate wishlist

    def __str__(self):
        return f"{self.user.username} - {self.product.name}"

