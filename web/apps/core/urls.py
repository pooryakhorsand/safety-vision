from django.urls import path

from apps.core import views

app_name = "core"

urlpatterns = [
    path("system/status/", views.system_status, name="system_status"),
    path("engine/heartbeat/", views.engine_heartbeat, name="engine_heartbeat"),
]
