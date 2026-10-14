"""API routes for the engine, mounted under /api/ (see web_config/urls.py)."""

from django.urls import path

from apps.cameras import api

app_name = "cameras_api"

urlpatterns = [
    path("engine/cameras/", api.engine_camera_list, name="engine_cameras"),
]
