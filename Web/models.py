from django.db import models
from django.conf import settings
from accounts.models import Address
from products.models import ProductVariant,Product
class BaseAuditModel(models.Model):
    is_active = models.BooleanField(default=True)
    is_deleted = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    modified_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="%(class)s_created")
    modified_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="%(class)s_modified")

    class Meta:
        abstract = True
class Cart(BaseAuditModel):
    user = models.ForeignKey( settings.AUTH_USER_MODEL, on_delete=models.CASCADE, null=True, blank=True, related_name="carts" )
    session_key = models.CharField(max_length=40, null=True, blank=True)
    def __str__(self):
        return f"Cart ({self.user or self.session_key})"

# Create your models here.
class CartItem(BaseAuditModel):
    cart = models.ForeignKey( Cart, related_name="items", on_delete=models.CASCADE )
    product = models.ForeignKey( "products.Product", on_delete=models.CASCADE )
    variant = models.ForeignKey( "products.ProductVariant", on_delete=models.SET_NULL, null=True, blank=True )
    quantity = models.PositiveIntegerField(default=1)
    price = models.DecimalField( max_digits=12, decimal_places=2, help_text="Price at the time of adding to cart" )
    class Meta:
        unique_together = ("cart", "product", "variant")
    def __str__(self):
        return f"{self.product} x {self.quantity}"

import uuid

class Order(BaseAuditModel):
    PAYMENT_METHODS = [
        ('cod', 'Cash on Delivery'),
        ('card', 'Card Payment'),
        ('wallet', 'Wallet'),
    ]
    ORDER_STATUS = [
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('shipped', 'Shipped'),
        ('delivered', 'Delivered'),
        ('cancelled', 'Cancelled'),
        ('returned', 'Cancelled'),
        ('failed', 'Payment Failed'),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="orders")
    billing_address = models.ForeignKey(Address, on_delete=models.SET_NULL, null=True, blank=True, related_name="billing_orders")
    shipping_address = models.ForeignKey(Address, on_delete=models.SET_NULL, null=True, blank=True, related_name="shipping_orders")
    order_number = models.CharField(max_length=20, unique=True, blank=True)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    shipping_charges = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    payment_method = models.CharField(max_length=10, choices=PAYMENT_METHODS, default='cod')
    status = models.CharField(max_length=20, choices=ORDER_STATUS, default='pending')
    payment_status = models.CharField(max_length=20, choices=ORDER_STATUS, default='pending')
    placed_at = models.DateTimeField(auto_now_add=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    transaction_id = models.CharField(max_length=100, blank=True, null=True)
    notes = models.TextField(blank=True, null=True)

    def generate_order_number(self):
        return f"ORD-{uuid.uuid4().hex[:8].upper()}"

    def save(self, *args, **kwargs):
        if not self.order_number:
            self.order_number = self.generate_order_number()
        super().save(*args, **kwargs)
    def __str__(self):
        return f"Order {self.order_number or self.id} - {self.user}"


class OrderItem(BaseAuditModel):
    order = models.ForeignKey(Order, related_name="items", on_delete=models.CASCADE)
    product = models.ForeignKey(Product, on_delete=models.SET_NULL, null=True)
    variant = models.ForeignKey(ProductVariant, on_delete=models.SET_NULL, null=True, blank=True)
    quantity = models.PositiveIntegerField(default=1)
    price = models.DecimalField(max_digits=12, decimal_places=2, help_text="Price at time of order")
    total = models.DecimalField(max_digits=12, decimal_places=2, help_text="price * quantity")

    def save(self, *args, **kwargs):
        self.total = self.price * self.quantity
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.product} x {self.quantity}"


class SupportTicket(models.Model):

    SUPPORT_CHOICES = [
        ("order", "Order Issue"),
        ("payment", "Payment Issue"),
        ("return", "Returns / Refunds"),
        ("account", "Account / Security"),
        ("other", "Others"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True
    )

    name = models.CharField(max_length=255)
    email = models.EmailField()
    support_type = models.CharField(max_length=20, choices=SUPPORT_CHOICES)
    subject = models.CharField(max_length=255)
    message = models.TextField()
    attachment = models.FileField(upload_to="support_attachments/", null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} - {self.subject}"



class OrderRequest(BaseAuditModel):
    REQUEST_TYPE_CHOICES = [
        ("cancel", "Cancel"),
        ("return", "Return"),
    ]

    PREFERRED_ACTION_CHOICES = [
        ("", "null"),
        ("refund", "Refund"),
        ("replacement", "Replacement"),
    ]

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="requests")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    request_type = models.CharField(max_length=10, choices=REQUEST_TYPE_CHOICES)
    items = models.ManyToManyField(OrderItem, blank=True, null=True)
    reason = models.TextField(blank=True, null=True)
    preferred_action = models.CharField(max_length=20, choices=PREFERRED_ACTION_CHOICES, null=True, blank=True)
    attachment = models.FileField(upload_to="order_requests/", null=True, blank=True)
    status = models.CharField(max_length=20, default="pending")

    def __str__(self):
        return f"{self.order.order_number} - {self.request_type} by {self.user.email}"

class UserWallet(BaseAuditModel):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="wallet"
    )
    balance = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    def __str__(self):
        return f"{self.user.email} Wallet - {self.balance}"

class UserWalletTransaction(BaseAuditModel):
    TRANSACTION_TYPES = (
        ("credit", "Credit"),
        ("debit", "Debit"),
        ("returnorder", "Return Order"),
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="wallet_transactions"
    )

    wallet = models.ForeignKey(
        UserWallet,
        on_delete=models.CASCADE,
        related_name="transactions"
    )

    transaction_type = models.CharField(max_length=20, choices=TRANSACTION_TYPES)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    description = models.TextField(blank=True, null=True)

    order = models.ForeignKey(
        "Order",
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.email} - {self.transaction_type} - {self.amount}"

from django.conf import settings
from django.db import models


class OrderRequestComment(BaseAuditModel):

    request = models.ForeignKey(
        "OrderRequest",
        on_delete=models.CASCADE,
        related_name="comments"
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )
    status = models.CharField(max_length=50)
    comment = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    is_admin = models.BooleanField(default=False)

    def __str__(self):
        return f"Request #{self.request.id} - {self.status}"