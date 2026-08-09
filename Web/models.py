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
import qrcode
from io import BytesIO
from django.core.files import File
class Order(BaseAuditModel):
    PAYMENT_METHODS = [
        ('cod', 'Cash on Delivery'),
        ('card', 'Card Payment'),
        ('wallet', 'Wallet'),
    ]
    ORDER_STATUS = [
        ('pending', 'Pending'),
        ('submited', 'Submited'),
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
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    shipping_charges = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    payment_method = models.CharField(max_length=10, choices=PAYMENT_METHODS, default='cod')
    status = models.CharField(max_length=20, choices=ORDER_STATUS, default='pending')
    payment_status = models.CharField(max_length=20, choices=ORDER_STATUS, default='pending')
    placed_at = models.DateTimeField(auto_now_add=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    transaction_id = models.CharField(max_length=100, blank=True, null=True)
    notes = models.TextField(blank=True, null=True)
    qr_code = models.ImageField(upload_to='qrcodes/', blank=True, null=True)

    def generate_order_number(self):
        return f"ORD-{uuid.uuid4().hex[:8].upper()}"
    

    def save(self, *args, **kwargs):
        if self.pk:
            old_order = Order.objects.get(pk=self.pk)
            if old_order.status not in ['cancelled', 'returned'] and self.status in ['cancelled', 'returned']:
                for item in self.items.all():
                    if item.variant:
                        item.variant.stock_quantity += item.quantity
                        item.variant.save()
                        item.variant.product.sold -= item.quantity
                        item.variant.product.save()
        if not self.order_number:
            self.order_number = self.generate_order_number()
            
        if not self.qr_code:
            qr_data = f"Order No: {self.order_number}\nName: {self.user.full_name}\nshipping Address: {self.shipping_address.street_address},{self.shipping_address.city},{self.shipping_address.state},{self.shipping_address.country}\nBilling Address: {self.billing_address.street_address},{self.billing_address.city},{self.billing_address.state},{self.billing_address.country}\nTotal: {self.total_amount}"
            qr_img = qrcode.make(qr_data)
            blob = BytesIO()
            qr_img.save(blob, 'PNG')
            self.qr_code.save(f"order_{self.order_number}.png", File(blob), save=False)

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
        if not self.pk:  
            if self.variant:
                if self.variant.stock_quantity < self.quantity:
                    raise ValidationError("Not enough stock available")

                self.variant.stock_quantity -= self.quantity
                self.variant.save()
                self.variant.product.sold += self.quantity
                self.variant.product.save()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.product} x {self.quantity}"
from accounts.models import User
class OrderSeenLog(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    order = models.ForeignKey("Order", on_delete=models.CASCADE, related_name="seen_logs")
    created_at = models.DateTimeField(auto_now_add=True)

    is_seen_by_admin = models.BooleanField(default=True)

    def __str__(self):
        return f"Order #{self.order.id} - {self.user.username}"

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


# models.py
# models.py

from django.conf import settings
from django.db import models


class Notification(BaseAuditModel):

    NOTIFICATION_TYPES = [
        ('order_placed', 'Order Placed'),
        ('order_dispatched', 'Order Dispatched'),
        ('order_delivered', 'Order Delivered'),
        ('order_canceled', 'Order Canceled'),
        ('order_status', 'Order Status'),
        ('promotion', 'Promotion / Offer'),
    ]

    title = models.CharField(max_length=255)
    message = models.TextField()
    notification_type = models.CharField(max_length=50,choices=NOTIFICATION_TYPES)
    # Optional relations
    order = models.ForeignKey('Order',on_delete=models.CASCADE,null=True,blank=True)
    promotion = models.ForeignKey('products.Promotion',on_delete=models.CASCADE,null=True,blank=True)
    is_general = models.BooleanField(default=False)

    def __str__(self):
        return self.title


class NotificationRecipient(models.Model):
    notification = models.ForeignKey(Notification,on_delete=models.CASCADE,related_name="recipients")
    user = models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.CASCADE,related_name="user_notifications")
    is_read = models.BooleanField(default=False)
    seen_at = models.DateTimeField(null=True, blank=True)
    class Meta:
        unique_together = ('notification', 'user')
    def __str__(self):
        return f"{self.user} - {self.notification.title}"





class ChatThread(BaseAuditModel):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    product_id = models.IntegerField(null=True, blank=True)
    variant_id = models.IntegerField(null=True, blank=True)

    def __str__(self):
        return f"Thread {self.id} - User {self.user_id}"


class ChatMessage(BaseAuditModel):
    SENDER_TYPE = (
        ('user', 'User'),
        ('admin', 'Admin'),
    )

    thread = models.ForeignKey(ChatThread, on_delete=models.CASCADE, related_name="messages")
    sender_type = models.CharField(max_length=10, choices=SENDER_TYPE)
    message = models.TextField()

    def __str__(self):
        return f"{self.sender_type}: {self.message[:20]}"


class WishToBuy(BaseAuditModel):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    product = models.ForeignKey("products.Product", on_delete=models.CASCADE)
    variant = models.ForeignKey("products.ProductVariant", on_delete=models.CASCADE,null=True, blank=True)


    def __str__(self):
        return f"{self.user} wants {self.product}"

class NewsletterSubscriber(models.Model):
    email = models.EmailField(unique=True)
    is_active = models.BooleanField(default=True)
    subscribed_at = models.DateTimeField(auto_now_add=True)
    unsubscribed_at = models.DateTimeField(null=True, blank=True)
 
    def __str__(self):
        return self.email