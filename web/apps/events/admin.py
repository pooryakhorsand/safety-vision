"""Django admin registration (for superusers at /system-admin/)."""

from django.contrib import admin

from apps.events.models import Event


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ("started_at", "camera_name", "module_key", "event_type", "track_id", "severity", "status")
    list_filter = ("module_key", "event_type", "severity", "status", "camera_name")
    search_fields = ("uid", "camera_name", "event_type", "note")
    date_hierarchy = "started_at"
    readonly_fields = ("uid", "created_at", "updated_at")
