from django.urls import path

from apps.events import views

app_name = "events"

urlpatterns = [
    path("", views.event_list, name="list"),
    path("<int:pk>/", views.event_detail, name="detail"),
    path("<int:pk>/acknowledge/", views.event_acknowledge, name="acknowledge"),
    path("<int:pk>/assign-person/", views.event_assign_person, name="assign_person"),
    path("<int:pk>/snapshot/", views.event_snapshot, name="snapshot"),
]
