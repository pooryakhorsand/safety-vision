"""Camera management pages, mounted under /cameras/ (see web_config/urls.py)."""

from django.urls import path

from apps.cameras import views

app_name = "cameras"

urlpatterns = [
    path("", views.camera_list, name="list"),
    path("new/", views.camera_create, name="create"),
    path("<int:pk>/edit/", views.camera_edit, name="edit"),
    path("<int:pk>/toggle/", views.camera_toggle, name="toggle"),
    path("<int:pk>/delete/", views.camera_delete, name="delete"),
]
