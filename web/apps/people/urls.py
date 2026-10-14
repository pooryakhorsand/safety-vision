from django.urls import path

from apps.people import views

app_name = "people"

urlpatterns = [
    path("", views.person_list, name="list"),
    path("new/", views.person_create, name="create"),
    path("<int:pk>/", views.person_detail, name="detail"),
    path("<int:pk>/edit/", views.person_edit, name="edit"),
    path("<int:pk>/toggle-active/", views.person_toggle_active, name="toggle_active"),
]
