"""API routes, mounted under /api/ (see web_config/urls.py)."""

from django.urls import path

from apps.events import api

app_name = "events_api"

urlpatterns = [
    path("events/", api.ingest_event, name="ingest"),
    path("events/summary/", api.events_summary, name="summary"),
]
