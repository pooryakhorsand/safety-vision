"""WSGI entry point (used by the production server, Waitress)."""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "web_config.settings")

application = get_wsgi_application()
