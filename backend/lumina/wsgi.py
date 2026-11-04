"""
WSGI config for lumina project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/6.1/howto/deployment/wsgi/
"""

import os

from django.core.wsgi import get_wsgi_application

# Gunakan package settings (lumina.settings.__init__) untuk memilih environment
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "lumina.settings")

application = get_wsgi_application()