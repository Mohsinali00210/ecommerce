"""
Django settings for shanzeeecommerce.

All secrets and environment-specific values come from environment variables
(loaded from .env in development). See .env.example for the full list.
"""
import os
import warnings
from datetime import timedelta
from pathlib import Path

from celery.schedules import crontab
from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def env(name, default=None):
    return os.environ.get(name, default)


def env_bool(name, default=False):
    v = os.environ.get(name)
    return default if v is None else v.strip().lower() in ("1", "true", "yes", "on")


def env_list(name, default=""):
    return [x.strip() for x in env(name, default).split(",") if x.strip()]


# ---------------------------------------------------------------------------
# Core / security
# ---------------------------------------------------------------------------
DEBUG = env_bool("DJANGO_DEBUG", False)

SECRET_KEY = env("DJANGO_SECRET_KEY")
if not SECRET_KEY:
    if DEBUG:
        SECRET_KEY = "dev-only-insecure-key-set-DJANGO_SECRET_KEY-in-production"
        warnings.warn("DJANGO_SECRET_KEY not set - using an insecure development key.")
    else:
        raise ImproperlyConfigured("Set DJANGO_SECRET_KEY in the environment (.env).")

ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "127.0.0.1,localhost")
CSRF_TRUSTED_ORIGINS = env_list("DJANGO_CSRF_TRUSTED_ORIGINS", "")
SITE_URL = env("SITE_URL", "https://shanzee.com").rstrip("/")

if not DEBUG:
    SECURE_SSL_REDIRECT = env_bool("DJANGO_SECURE_SSL_REDIRECT", True)
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = int(env("DJANGO_HSTS_SECONDS", "3600"))
    SECURE_HSTS_INCLUDE_SUBDOMAINS = False
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_REFERRER_POLICY = "same-origin"
    X_FRAME_OPTIONS = "DENY"

# ---------------------------------------------------------------------------
# Applications
# ---------------------------------------------------------------------------
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    'allauth',
    'allauth.account',
    'allauth.socialaccount',
    'allauth.socialaccount.providers.google',

    'rest_framework',
    'django_filters',
    'drf_spectacular',

    'accounts',
    'products',
    'Web',
    'reports',
    'channels',
    'chat',
    'UserPanel',
    'couriers',
    'adminpanel',
    'payments',
    'storefront',
    'django.contrib.sitemaps',
]

MIDDLEWARE = [
    "accounts.error_logging.RequestIDMiddleware",
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    "accounts.error_logging.ErrorLogMiddleware",
    "adminpanel.session.AdminSessionMiddleware",   # idle / absolute timeout for staff
    "accounts.rbac.AdminAccessMiddleware",          # role-based access to admin URLs
    "adminpanel.unseen.UnseenMiddleware",           # "new since last visit" badges
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'allauth.account.middleware.AccountMiddleware',
]
AUTH_USER_MODEL = 'accounts.User'

ROOT_URLCONF = 'shanzeeecommerce.urls'
TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                "products.context_processors.admin_order_counts",
                "adminpanel.context_processors.admin_ui",
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

ASGI_APPLICATION = "shanzeeecommerce.asgi.application"
WSGI_APPLICATION = 'shanzeeecommerce.wsgi.application'

# ---------------------------------------------------------------------------
# Redis: channels, cache (rate limits), Celery
# ---------------------------------------------------------------------------
REDIS_URL = env("REDIS_URL", "")

if REDIS_URL:
    CHANNEL_LAYERS = {"default": {"BACKEND": "channels_redis.core.RedisChannelLayer",
                                  "CONFIG": {"hosts": [REDIS_URL]}}}
    CACHES = {"default": {"BACKEND": "django.core.cache.backends.redis.RedisCache",
                          "LOCATION": REDIS_URL}}
else:
    CHANNEL_LAYERS = {"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}
    CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
    # django-ratelimit warns that locmem isn't shared between processes; fine for dev.
    SILENCED_SYSTEM_CHECKS = ["django_ratelimit.E003", "django_ratelimit.W001"]

# Behind nginx set RATELIMIT_IP_META_KEY=HTTP_X_REAL_IP (and proxy_set_header X-Real-IP $remote_addr)
# otherwise every visitor shares the proxy's IP for login/OTP rate limits.
RATELIMIT_IP_META_KEY = env("RATELIMIT_IP_META_KEY", "REMOTE_ADDR")

CELERY_BROKER_URL = env("CELERY_BROKER_URL", REDIS_URL or "memory://")
CELERY_RESULT_BACKEND = env("CELERY_RESULT_BACKEND", None)
# Without Redis, run tasks inline so the site still works in development.
CELERY_TASK_ALWAYS_EAGER = env_bool("CELERY_TASK_ALWAYS_EAGER", not REDIS_URL)
CELERY_TASK_EAGER_PROPAGATES = False
CELERY_TIMEZONE = "Asia/Karachi"
CELERY_TASK_ACKS_LATE = True
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
CELERY_TASK_TIME_LIMIT = 300

COURIER_POLL_MINUTES = int(env("COURIER_POLL_MINUTES", "30"))
COURIER_TRACK_MAX_DAYS = int(env("COURIER_TRACK_MAX_DAYS", "45"))
COURIER_ENCRYPTION_KEY = env("COURIER_ENCRYPTION_KEY", "")
COURIER_TRUST_X_FORWARDED_FOR = env_bool("COURIER_TRUST_X_FORWARDED_FOR", False)

CELERY_BEAT_SCHEDULE = {
    "couriers-poll-shipments": {
        "task": "couriers.tasks.poll_active_shipments",
        "schedule": timedelta(minutes=COURIER_POLL_MINUTES),
    },
    "payments-expire-unpaid": {
        "task": "payments.tasks.expire_unpaid_online_orders",
        "schedule": timedelta(minutes=10),
    },
    "adminpanel-scheduled-backup": {
        "task": "adminpanel.tasks.scheduled_backup",
        "schedule": crontab(minute=7),   # checks every hour; runs at the hour set in Store settings
    },
    "couriers-sync-cities": {
        "task": "couriers.tasks.sync_all_cities",
        "schedule": crontab(hour=4, minute=17, day_of_week="mon"),
    },
}

# ---------------------------------------------------------------------------
# REST / auth
# ---------------------------------------------------------------------------
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": (
        "rest_framework.permissions.IsAuthenticated",
    ),
    "EXCEPTION_HANDLER": "adminpanel.drf.exception_handler",
}
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=60),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
}

SITE_ID = 1

# ---------------------------------------------------------------------------
# Sessions (staff sessions also end when the browser closes - set at login)
# ---------------------------------------------------------------------------
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
CSRF_FAILURE_VIEW = "adminpanel.views.csrf_failure"
ADMIN_SESSION_IDLE_MINUTES = int(env("ADMIN_SESSION_IDLE_MINUTES", "60"))
ADMIN_SESSION_MAX_HOURS = int(env("ADMIN_SESSION_MAX_HOURS", "12"))
ADMIN_SESSION_WARNING_SECONDS = int(env("ADMIN_SESSION_WARNING_SECONDS", "120"))
ADMIN_JWT_MINUTES = int(env("ADMIN_JWT_MINUTES", "15"))

AUTHENTICATION_BACKENDS = (
    'django.contrib.auth.backends.ModelBackend',
    'allauth.account.auth_backends.AuthenticationBackend',
)

LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "home:home"
LOGOUT_REDIRECT_URL = '/'
ACCOUNT_LOGIN_METHODS = {"email"}
ACCOUNT_SIGNUP_FIELDS = ["email*", "password1*", "password2*"]
ACCOUNT_EMAIL_VERIFICATION = "none"

SOCIALACCOUNT_AUTO_SIGNUP = True
SOCIALACCOUNT_LOGIN_ON_GET = True
SOCIALACCOUNT_QUERY_EMAIL = True
SOCIALACCOUNT_EMAIL_REQUIRED = True
SOCIALACCOUNT_ADAPTER = 'accounts.adapters.MySocialAccountAdapter'

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': env("DB_NAME", "ecommerce"),
        'USER': env("DB_USER", "postgres"),
        'PASSWORD': env("DB_PASSWORD", ""),
        'HOST': env("DB_HOST", "localhost"),
        'PORT': env("DB_PORT", "5432"),
        'CONN_MAX_AGE': 60,
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'
# Never served by the web server: bank receipts etc. (served by permission-checked views)
PRIVATE_MEDIA_ROOT = Path(env("PRIVATE_MEDIA_ROOT", str(BASE_DIR / "private_media")))
# Database backups (keep outside the web root; ideally on another disk)
BACKUP_DIR = Path(env("BACKUP_DIR", str(BASE_DIR / "backups")))
FILE_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024
DATA_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024

# ---------------------------------------------------------------------------
# Email (Hostinger SMTP by default; password only from the environment)
# ---------------------------------------------------------------------------
ADMIN_EMAIL = env("ADMIN_EMAIL", "admin@shanzee.com")
EMAIL_BACKEND = env("SMTP_BACKEND", "django.core.mail.backends.smtp.EmailBackend")
EMAIL_HOST = env("SMTP_HOST", "smtp.hostinger.com")
EMAIL_PORT = int(env("SMTP_PORT", "465"))
EMAIL_USE_SSL = env_bool("SMTP_USE_SSL", True)   # Hostinger 465 = SSL
EMAIL_USE_TLS = env_bool("SMTP_USE_TLS", False)  # mutually exclusive with SSL
EMAIL_HOST_USER = env("SMTP_USER", "admin@shanzee.com")
EMAIL_HOST_PASSWORD = env("SMTP_PASSWORD", "")
EMAIL_TIMEOUT = 20
DEFAULT_FROM_EMAIL = env("SMTP_FROM", "shanzee@shanzee.com")

# ---------------------------------------------------------------------------
# Logging: logs/app.log (everything), logs/error.log (errors only),
# logs/security.log (audit trail). JSON lines, rotated at 10 MB x 10 files.
# ---------------------------------------------------------------------------
LOG_DIR = Path(env("LOG_DIR", str(BASE_DIR / "logs")))
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_LEVEL = env("LOG_LEVEL", "INFO")


def _rotating(filename, level="INFO"):
    return {"class": "logging.handlers.RotatingFileHandler", "filename": str(LOG_DIR / filename),
            "maxBytes": 10 * 1024 * 1024, "backupCount": 10, "encoding": "utf-8",
            "formatter": "json", "level": level}


LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "json": {"()": "accounts.log_formatters.JsonFormatter"},
        "console": {"format": "%(asctime)s %(levelname)s %(name)s: %(message)s"},
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "console"},
        "app_file": _rotating("app.log", LOG_LEVEL),
        "error_file": _rotating("error.log", "ERROR"),
        "security_file": _rotating("security.log", "INFO"),
    },
    "loggers": {
        "app": {"handlers": ["console", "app_file", "error_file"], "level": LOG_LEVEL, "propagate": False},
        "security": {"handlers": ["security_file", "console"], "level": "INFO", "propagate": False},
        "couriers": {"handlers": ["console", "app_file", "error_file"],
                     "level": env("COURIER_LOG_LEVEL", "INFO"), "propagate": False},
        "django.request": {"handlers": ["app_file", "error_file"], "level": "WARNING", "propagate": False},
        "django.security": {"handlers": ["security_file"], "level": "INFO", "propagate": False},
    },
}
