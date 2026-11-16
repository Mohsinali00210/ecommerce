from django.db import models
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.conf import settings

# ------------------------------
# User Manager
# ------------------------------
class UserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError("Email is required")
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        return self.create_user(email, password, **extra_fields)


# ------------------------------
# User & Role Models
# ------------------------------
class Role(models.Model):
    ROLE_CHOICES = [
        ("CUSTOMER", "Customer"),
        ("ADMIN", "Admin"),
        ("VENDOR", "Vendor")
    ]
    name = models.CharField(max_length=20, choices=ROLE_CHOICES, unique=True)

    def __str__(self):
        return self.name


class User(AbstractBaseUser, PermissionsMixin):
    full_name = models.CharField(max_length=255, null=True, blank=True)
    username = models.CharField(max_length=255, null=True, blank=True)
    email = models.EmailField(unique=True, null=True, blank=True)
    mobile = models.CharField(max_length=15, unique=True, null=True, blank=True)
    dob = models.DateField(null=True, blank=True)
    gender = models.CharField(max_length=10, null=True, blank=True)
    avatar = models.ImageField(upload_to='avatars/', null=True, blank=True)
    roles = models.ManyToManyField(Role, related_name='users')
    is_active = models.BooleanField(default=True)
    is_varified = models.BooleanField(default=False)

    is_staff = models.BooleanField(default=False)
    date_joined = models.DateTimeField(auto_now_add=True)
    referral_code = models.CharField(max_length=20, null=True, blank=True)

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []

    objects = UserManager()
    BLOCK_TYPE_CHOICES = [
        ('temporary', 'Temporary'),
        ('permanent', 'Permanent'),
    ]

    is_blocked_from_ordering = models.BooleanField(default=False)
    block_type = models.CharField(max_length=10, choices=BLOCK_TYPE_CHOICES, null=True, blank=True)
    blocked_until = models.DateTimeField(null=True, blank=True)
    block_reason = models.CharField(max_length=255, blank=True)

    def is_order_blocked(self):
        """True if the user is currently blocked from placing orders."""
        if not self.is_blocked_from_ordering:
            return False
        if self.block_type == 'temporary' and self.blocked_until and timezone.now() >= self.blocked_until:
            return False  # temporary block has expired
        return True
    def get_full_name(self):
        return self.full_name or self.username or self.email.split("@")[0] or self.mobile or ""
    def __str__(self):
        return self.full_name or self.email or self.mobile


# ------------------------------
# OTP & Session Models
# ------------------------------
class OTP(models.Model):
    PURPOSE_CHOICES = [
        ("REGISTER", "Register"),
        ("LOGIN", "Login"),
        ("RESET_PASSWORD", "Reset Password"),
        ("ORDER_CONFIRM", "Order Confirm")
    ]
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='otps')
    code = models.CharField(max_length=6)
    purpose = models.CharField(max_length=20, choices=PURPOSE_CHOICES)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()

    def __str__(self):
        return f"{self.user} - {self.purpose}"


class UserSession(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='sessions')
    refresh_token = models.TextField()
    device_info = models.CharField(max_length=255, null=True, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()


# ------------------------------
# Address Model
# ------------------------------
class Address(models.Model):
    ADDRESS_TYPES = [
        ('billing', 'Billing'),
        ('shipping', 'Shipping'),
    ]
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="addresses")
    address_type = models.CharField(max_length=10, choices=ADDRESS_TYPES, default='shipping')
    full_name = models.CharField(max_length=255)
    phone = models.CharField(max_length=20)
    street_address = models.TextField()
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=100, blank=True, null=True)
    country = models.CharField(max_length=100, default="Pakistan")
    postal_code = models.CharField(max_length=20)
    is_default = models.BooleanField(default=False)


    def __str__(self):
        return f"{self.full_name} - {self.address_type}"


# ------------------------------
# Login History & Security
# ------------------------------
class LoginHistory(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='login_history')
    ip_address = models.GenericIPAddressField()
    user_agent = models.CharField(max_length=255)
    login_at = models.DateTimeField(auto_now_add=True)


# ------------------------------
# Admin User Management Logs
# ------------------------------
class AdminActionLog(models.Model):
    ACTION_CHOICES = [
        ("ACTIVATE_USER", "Activate User"),
        ("DEACTIVATE_USER", "Deactivate User"),
        ("RESET_PASSWORD", "Reset Password")
    ]
    admin_user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='admin_actions')
    target_user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='targeted_by_admin')
    action = models.CharField(max_length=50, choices=ACTION_CHOICES)
    timestamp = models.DateTimeField(auto_now_add=True)

# models.py
from django.conf import settings

class ErrorLog(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )
    endpoint = models.CharField(max_length=255)
    method = models.CharField(max_length=10)
    error_message = models.TextField()
    stack_trace = models.TextField(null=True, blank=True)
    status_code = models.IntegerField()

    request_data = models.JSONField(null=True, blank=True)
    query_params = models.JSONField(null=True, blank=True)

    severity = models.CharField(max_length=10, default="ERROR", db_index=True)
    request_id = models.CharField(max_length=32, blank=True, db_index=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=255, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)



class SecurityEvent(models.Model):
    """Audit trail: logins, logouts, failed logins, denied access, session
    timeouts and sensitive admin actions."""
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    event = models.CharField(max_length=50, db_index=True)
    severity = models.CharField(max_length=10, default="INFO", db_index=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                             related_name="security_events")
    username = models.CharField(max_length=254, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=255, blank=True)
    path = models.CharField(max_length=255, blank=True)
    method = models.CharField(max_length=10, blank=True)
    request_id = models.CharField(max_length=32, blank=True)
    details = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.created_at:%Y-%m-%d %H:%M} {self.event} {self.username}"


class AdminAccess(models.Model):
    """No table: only carries the admin-panel permissions used for role-based
    access (assigned to roles = Django groups)."""

    class Meta:
        managed = False
        default_permissions = ()
        permissions = [
            ("view_dashboard", "Admin: view dashboard & reports"),
            ("view_catalog", "Admin: view products, categories, brands, inventory"),
            ("manage_catalog", "Admin: create/edit/delete catalog items"),
            ("view_orders", "Admin: view orders & order requests"),
            ("manage_orders", "Admin: update orders, approve requests"),
            ("manage_shipping", "Admin: book/cancel shipments, courier settings"),
            ("view_customers", "Admin: view customers"),
            ("manage_customers", "Admin: block/unblock customers"),
            ("manage_support", "Admin: chat, tickets, product questions"),
            ("manage_marketing", "Admin: promotions, blog, top bar"),
            ("manage_finance", "Admin: wallet withdrawals"),
            ("view_logs", "Admin: view error & security logs"),
            ("manage_roles", "Admin: assign admin roles"),
            ("manage_settings", "Admin: store settings (payments, emails)"),
            ("manage_backups", "Admin: database backups & restore (super admins)"),
        ]
