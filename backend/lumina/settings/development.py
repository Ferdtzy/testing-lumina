"""
Development settings untuk proyek Lumina.

Digunakan saat DJANGO_ENV=development (default).
"""
import os

from lumina.settings.base import _get_env_or_raise  # noqa: F401
from lumina.settings.base import *  # noqa: F401,F403

# ── Security ────────────────────────────────────────────────────────────────
DEBUG = True

SECRET_KEY = _get_env_or_raise("DJANGO_SECRET_KEY", " (security critical)")

ALLOWED_HOSTS = [host for host in os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1,testserver").split(",") if host or host == "testserver"]

# ── Database ────────────────────────────────────────────────────────────────
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": _get_env_or_raise("DB_NAME", " (database name required)"),
        "USER": _get_env_or_raise("DB_USER", " (database username required)"),
        "PASSWORD": _get_env_or_raise("DB_PASSWORD", " (database password required)"),
        "HOST": os.environ.get("DB_HOST", "127.0.0.1"),
        "PORT": os.environ.get("DB_PORT", "5433"),
    }
}

# ── CORS ────────────────────────────────────────────────────────────────────
CORS_ALLOWED_ORIGINS = [
    origin
    for origin in os.environ.get(
        "CORS_ALLOWED_ORIGINS",
        "http://localhost:3000,http://127.0.0.1:3000",
    ).split(",")
    if origin
]

CORS_ALLOW_CREDENTIALS = True

# ── Email ───────────────────────────────────────────────────────────────────
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# ── DRF ─────────────────────────────────────────────────────────────────────
REST_FRAMEWORK["DEFAULT_RENDERER_CLASSES"] = [  # noqa: F405
    "rest_framework.renderers.JSONRenderer",
    "rest_framework.renderers.BrowsableAPIRenderer",
]

# Local research uploads: allow normal retries without disabling throttling.
REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"] = {  # noqa: F405
    **REST_FRAMEWORK.get("DEFAULT_THROTTLE_RATES", {}),  # noqa: F405
    "upload": os.environ.get("UPLOAD_THROTTLE_RATE", "30/hour"),
}
