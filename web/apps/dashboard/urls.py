from django.urls import path

from apps.dashboard import views

app_name = "dashboard"

urlpatterns = [
    path("overview/", views.overview, name="overview"),
    path("live/", views.live, name="live"),
    path("settings/", views.settings_home, name="settings"),
]
