import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

REPO_ROOT = Path(os.environ.get("AICMO_REPO", ".")).resolve()
if (
    not (REPO_ROOT / "registry/capabilities.yaml").is_file()
    or not (REPO_ROOT / "workflows").is_dir()
):
    reason = "AICMO_REPO must point to the platform repository"
    raise ImproperlyConfigured(reason)
SECRET_KEY = os.environ.get("AICMO_WEB_SECRET_KEY", "")
_MIN_KEY_LENGTH = 50
if len(SECRET_KEY) < _MIN_KEY_LENGTH:
    reason = "AICMO_WEB_SECRET_KEY must be a private random value of at least 50 characters"
    raise ImproperlyConfigured(reason)
LOCAL_DEVELOPMENT = os.environ.get("AICMO_WEB_LOCAL") == "1"
if not LOCAL_DEVELOPMENT and not os.environ.get("AICMO_REPO"):
    reason = "AICMO_REPO is required outside local development"
    raise ImproperlyConfigured(reason)
DEBUG = False
ALLOWED_HOSTS = [
    value.strip()
    for value in os.environ.get("AICMO_WEB_HOSTS", "localhost,127.0.0.1,[::1]").split(",")
]
if "*" in ALLOWED_HOSTS or any(not value for value in ALLOWED_HOSTS):
    reason = "AICMO_WEB_HOSTS must list explicit hostnames"
    raise ImproperlyConfigured(reason)
ROOT_URLCONF = "aicmo.store_app.urls"
WSGI_APPLICATION = "aicmo.store_app.wsgi.application"
INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.admin",
    "aicmo.store_app",
]
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "aicmo.store_app.uploads.UploadCleanupMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ]
        },
    }
]
REPO_ROOT.joinpath(".aicmo").mkdir(exist_ok=True)
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": REPO_ROOT / ".aicmo/web.sqlite3",
        "OPTIONS": {"timeout": 10, "transaction_mode": "IMMEDIATE"},
    }
}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
LANGUAGE_CODE = "ko-kr"
TIME_ZONE = "Asia/Seoul"
USE_TZ = True
STATIC_URL = "/static/"
STATIC_ROOT = REPO_ROOT / ".aicmo/static"
LOGIN_URL = "/login/"
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "/login/"
SESSION_COOKIE_AGE = 60 * 60 * 8
SESSION_EXPIRE_AT_BROWSER_CLOSE = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_SECURE = not LOCAL_DEVELOPMENT
CSRF_COOKIE_SECURE = not LOCAL_DEVELOPMENT
SECURE_SSL_REDIRECT = not LOCAL_DEVELOPMENT
SECURE_HSTS_SECONDS = 0 if LOCAL_DEVELOPMENT else 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = not LOCAL_DEVELOPMENT
SECURE_HSTS_PRELOAD = not LOCAL_DEVELOPMENT
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"
DATA_UPLOAD_MAX_MEMORY_SIZE = 64 * 1024
DATA_UPLOAD_MAX_NUMBER_FIELDS = 30
DATA_UPLOAD_MAX_NUMBER_FILES = 1
# One bounded temporary handler also checks small files before form validation.
FILE_UPLOAD_HANDLERS = ["aicmo.store_app.uploads.PhotoUploadHandler"]
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 12},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
AUTHENTICATION_BACKENDS = ["aicmo.store_app.auth.LimitedBackend"]
# Request bodies and engine errors are not copied into web logs.
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"null": {"class": "logging.NullHandler"}},
    "loggers": {"django.request": {"handlers": ["null"], "propagate": False}},
}
