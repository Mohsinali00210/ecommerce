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

    def __str__(self):
        return self.full_name or self.email or self.mobile


# ------------------------------
# OTP & Session Models
# ------------------------------
class OTP(models.Model):
    PURPOSE_CHOICES = [
        ("REGISTER", "Register"),
        ("LOGIN", "Login"),
        ("RESET_PASSWORD", "Reset Password")
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

    created_at = models.DateTimeField(auto_now_add=True)
