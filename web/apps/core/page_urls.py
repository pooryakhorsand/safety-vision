"""Pages that belong to no app: first-run setup. Mounted at the root (see web_config/urls.py)."""

from django.urls import path

from apps.core import setup_views

urlpatterns = [
    path("setup/", setup_views.setup, name="setup"),
]
