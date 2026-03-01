from django.contrib import admin
from .models import Attribute_Types,ShippingMethod, ShippingZone, ShippingRule, ShippingProvider,TaxCategory, Warehouse
# Register your models here.
admin.site.register(Attribute_Types)
@admin.register(ShippingMethod)
class ShippingMethodAdmin(admin.ModelAdmin):
    list_display = (
        'name', 
        'shipping_type', 
        'base_cost', 
        'estimated_delivery_time', 
        'is_active', 
        'is_deleted'
    )
    list_filter = ('shipping_type', 'is_active', 'is_deleted')
    search_fields = ('name', 'description')
    readonly_fields = ('created_at', 'modified_at', 'created_by', 'modified_by')

    def save_model(self, request, obj, form, change):
        if not obj.pk:
            obj.created_by = request.user
        obj.modified_by = request.user
        super().save_model(request, obj, form, change)



class ShippingRuleInline(admin.TabularInline):
    model = ShippingRule
    extra = 1
    fields = ('shipping_method', 'condition_type', 'min_value', 'max_value', 'shipping_cost', 'is_active')

from django.contrib import admin
from .models import ShippingZone

@admin.register(ShippingZone)
class ShippingZoneAdmin(admin.ModelAdmin):
    # What to show in the list view
    list_display = ('name', 'country', 'state_region', 'is_active', 'is_deleted')
    list_filter = ('is_active', 'is_deleted', 'country')
    search_fields = ('name', 'country', 'zip_codes')
    
    # Makes selecting methods/providers much easier (Two-column interface)
    filter_horizontal = ('shipping_methods', 'shipping_providers')
    
    # Organize fields into sections
    fieldsets = (
        ('Zone Info', {
            'fields': ('name', 'is_active')
        }),
        ('Geography', {
            'fields': ('country', 'state_region', 'zip_codes')
        }),
        ('Assignments', {
            'fields': ('shipping_methods', 'shipping_providers')
        }),
        ('Audit Info', {
            'fields': ('created_by', 'modified_by', 'is_deleted'),
            'classes': ('collapse',)
        }),
    )

    def save_model(self, request, obj, form, change):
        if not obj.pk:
            obj.created_by = request.user
        obj.modified_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(ShippingProvider)
class ShippingProviderAdmin(admin.ModelAdmin):
    list_display = ('name', 'provider_code', 'rate_type', 'is_active')
    list_filter = ('rate_type', 'is_active', 'is_deleted')
    search_fields = ('name', 'provider_code')
    
    fieldsets = (
        ('Provider Details', {
            'fields': ('name', 'provider_code', 'is_active')
        }),
        ('API Credentials', {
            'fields': ('api_key', 'api_secret', 'account_number', 'api_endpoint')
        }),
        ('Services & Rates', {
            'fields': (
                'has_standard_delivery', 'has_express_delivery', 'has_overnight_delivery',
                'rate_type', 'markup_percentage', 'min_charge'
            )
        }),
        ('Tracking', {
            'fields': ('enable_tracking', 'auto_generate_label')
        }),
        ('Audit', {
            'fields': ('created_by', 'modified_by', 'is_deleted'),
            'classes': ('collapse',)
        }),
    )

    def save_model(self, request, obj, form, change):
        if not obj.pk:
            obj.created_by = request.user
        obj.modified_by = request.user
        super().save_model(request, obj, form, change)



@admin.register(TaxCategory)
class TaxCategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'percentage', )
    list_filter = ('is_active', 'is_deleted')
    search_fields = ('name',)

    def save_model(self, request, obj, form, change):
        if not obj.pk:
            obj.created_by = request.user
        obj.modified_by = request.user
        super().save_model(request, obj, form, change)

@admin.register(Warehouse)
class WarehouseAdmin(admin.ModelAdmin):
    list_display = ('name', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('name',)

    def save_model(self, request, obj, form, change):
        if not obj.pk:
            obj.created_by = request.user
        obj.modified_by = request.user
        super().save_model(request, obj, form, change)