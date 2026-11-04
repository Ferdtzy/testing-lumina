"""
ASGI config for lumina project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/6.1/howto/deployment/asgi/
"""

import os

from django.core.asgi import get_asgi_application

# Gunakan package settings (lumina.settings.__init__) untuk memilih environment
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "lumina.settings")

application = get_asgi_application()