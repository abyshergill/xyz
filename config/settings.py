"""
Django settings for YourTrolley (Multi-Store Food Stall Management Platform).

Security-hardened configuration using environment variables via django-environ.
SQLite is active by default for local development/testing. A fully configured
PostgreSQL block is provided (commented out) for production deployment.
"""

from pathlib import Path
import environ

BASE_DIR = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------------------
# Environment variables (django-environ)
# ---------------------------------------------------------------------------
env = environ.Env(
    DEBUG=(bool, False),
)
# Reads a .env file placed at the project root if present. In production the
# real environment variables (set by the host / systemd / Docker) take
# precedence over anything in .env.
environ.Env.read_env(BASE_DIR / ".env")

SECRET_KEY = env("DJANGO_SECRET_KEY", default="django-insecure-CHANGE-ME-IN-PRODUCTION")

DEBUG = env.bool("DEBUG", default=True)

ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=["calcomp.ai", "www.calcomp.ai", "143.198.161.140", "localhost", "127.0.0.1"])

# ---------------------------------------------------------------------------
# Applications
# ---------------------------------------------------------------------------
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",

    # Local apps
    "accounts",
    "stores",
    "orders",
    "analytics",
    "platform_admin",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",          # CSRF protection enforced globally
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "accounts.middleware.RoleBasedAccessMiddleware",       # custom RBAC guard, see accounts/middleware.py
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "stores.context_processors.owner_store",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Database — switches between SQLite and PostgreSQL based on DJANGO_USE_POSTGRES
# ---------------------------------------------------------------------------
if env.bool("DJANGO_USE_POSTGRES", default=False):
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": env("DJANGO_DB_NAME"),
            "USER": env("DJANGO_DB_USER"),
            "PASSWORD": env("DJANGO_DB_PASSWORD"),
            "HOST": env("DJANGO_DB_HOST", default="db"),
            "PORT": env("DJANGO_DB_PORT", default="5432"),
            "CONN_MAX_AGE": 60,
            "OPTIONS": {
                "sslmode": env("DJANGO_SSLMODE", default="prefer"),
            },
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }


# ---------------------------------------------------------------------------
# Custom user model
# ---------------------------------------------------------------------------
AUTH_USER_MODEL = "accounts.User"

AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
]

LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "accounts:dashboard_redirect"
LOGOUT_REDIRECT_URL = "accounts:login"

# ---------------------------------------------------------------------------
# Password validation (strong hashing + validators)
# ---------------------------------------------------------------------------
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 9}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# Argon2 is preferred (memory-hard, resistant to GPU cracking) and falls back
# to Django's default PBKDF2 hasher for compatibility.
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher",
]

# ---------------------------------------------------------------------------
# Internationalization
# ---------------------------------------------------------------------------
LANGUAGE_CODE = "en-us"
TIME_ZONE = env("DJANGO_TIME_ZONE", default="UTC")
USE_I18N = True
USE_TZ = True

# ---------------------------------------------------------------------------
# Static & media files
# ---------------------------------------------------------------------------
STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

# Image upload hard limits (defence-in-depth against DoS / storage abuse).
# Enforced again in stores/utils.py via Pillow validation.
MAX_UPLOAD_IMAGE_MB = 8
ALLOWED_IMAGE_EXTENSIONS = [".jpg", ".jpeg", ".png", ".webp"]
STORE_IMAGE_MAX_DIMENSION = 1600   # px, long edge
FOOD_ITEM_IMAGE_MAX_DIMENSION = 1200
CURRENCY_ICON_MAX_DIMENSION = 200   # small icon, doesn't need to be large

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ---------------------------------------------------------------------------
# Security hardening
# ---------------------------------------------------------------------------
# --- CSRF ---
CSRF_COOKIE_HTTPONLY = False  # must be readable by JS if you read the token for AJAX; template tag is preferred instead
CSRF_COOKIE_SAMESITE = "Lax"
CSRF_USE_SESSIONS = False
CSRF_TRUSTED_ORIGINS = env.list("DJANGO_CSRF_TRUSTED_ORIGINS", default=[])

# --- Sessions ---
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_AGE = 60 * 60 * 24 * 7  # 7 days
SESSION_EXPIRE_AT_BROWSER_CLOSE = False

# --- Clickjacking / MIME sniffing / XSS ---
X_FRAME_OPTIONS = "DENY"
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_BROWSER_XSS_FILTER = True  # legacy header, harmless to keep

# --- HTTPS enforcement (Caddy terminates TLS in front of this app) ---
# These are only turned on when DEBUG is False so local development over
# plain HTTP still works.
if not DEBUG:
    SECURE_SSL_REDIRECT = env.bool("DJANGO_SECURE_SSL_REDIRECT", default=True)
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 60 * 60 * 24 * 365
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    # Caddy sets X-Forwarded-Proto, so Django must trust that header to know
    # the original request was HTTPS.
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
else:
    SECURE_SSL_REDIRECT = False
    SESSION_COOKIE_SECURE = False
    CSRF_COOKIE_SECURE = False

# --- File upload limits (defense-in-depth, also see ALLOWED_IMAGE_EXTENSIONS) ---
DATA_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024   # 10 MB
FILE_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024
FILE_UPLOAD_PERMISSIONS = 0o644

# ---------------------------------------------------------------------------
# Logging (captures auth + access-control events for auditing)
# ---------------------------------------------------------------------------
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "[{asctime}] {levelname} {name}: {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "verbose"},
        "security_file": {
            "class": "logging.handlers.RotatingFileHandler",
            "filename": BASE_DIR / "logs" / "security.log",
            "maxBytes": 5 * 1024 * 1024,
            "backupCount": 5,
            "formatter": "verbose",
        },
    },
    "loggers": {
        "django.security": {"handlers": ["console", "security_file"], "level": "WARNING", "propagate": False},
        "accounts": {"handlers": ["console", "security_file"], "level": "INFO", "propagate": False},
        "orders": {"handlers": ["console", "security_file"], "level": "INFO", "propagate": False},
    },
}
(BASE_DIR / "logs").mkdir(exist_ok=True)

# ---------------------------------------------------------------------------
# Email (used for order confirmations / password resets)
# ---------------------------------------------------------------------------
EMAIL_BACKEND = env("DJANGO_EMAIL_BACKEND", default="django.core.mail.backends.console.EmailBackend")
EMAIL_HOST = env("DJANGO_EMAIL_HOST", default="")
EMAIL_PORT = env.int("DJANGO_EMAIL_PORT", default=587)
EMAIL_USE_TLS = env.bool("DJANGO_EMAIL_USE_TLS", default=True)
EMAIL_HOST_USER = env("DJANGO_EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = env("DJANGO_EMAIL_HOST_PASSWORD", default="")
DEFAULT_FROM_EMAIL = env("DJANGO_DEFAULT_FROM_EMAIL", default="no-reply@yourtrolley.example.com")

# ---------------------------------------------------------------------------
# Cache (used for login brute-force lockout tracking -- see accounts/throttling.py)
# ---------------------------------------------------------------------------
# --- ACTIVE: in-memory cache (fine for local dev / a single-process deploy) ---
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
    }
}

# --- PRODUCTION: swap to Redis (or Memcached) once running multiple Gunicorn
#     workers, so the brute-force lockout counters are shared across all of
#     them instead of being tracked separately per-process. Requires
#     `pip install django-redis`.
#
# CACHES = {
#     "default": {
#         "BACKEND": "django_redis.cache.RedisCache",
#         "LOCATION": env("DJANGO_REDIS_URL", default="redis://127.0.0.1:6379/1"),
#         "OPTIONS": {"CLIENT_CLASS": "django_redis.client.DefaultClient"},
#     }
# }

# ---------------------------------------------------------------------------
# Site base URL (used to build absolute QR-code target links)
# ---------------------------------------------------------------------------
SITE_BASE_URL = env("DJANGO_SITE_BASE_URL", default="http://localhost:8000")
