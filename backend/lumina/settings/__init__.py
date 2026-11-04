"""
Package settings untuk proyek Lumina.

Pilih modul settings berdasarkan environment variable DJANGO_ENV:
- development (default) -> lumina.settings.development
- production            -> lumina.settings.production
"""
import os

DJANGO_ENV = os.environ.get("DJANGO_ENV", "development")

if DJANGO_ENV == "production":
    from lumina.settings.production import *  # noqa: F401,F403
else:
    from lumina.settings.development import *  # noqa: F401,F403