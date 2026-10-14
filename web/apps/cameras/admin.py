"""Django admin registration (superusers only; day-to-day camera editing is on the Cameras page)."""

from django.contrib import admin

from apps.cameras.models import Camera


@admin.register(Camera)
class CameraAdmin(admin.ModelAdmin):
    list_display = ("name", "group", "modules", "is_enabled", "display_order")
    list_editable = ("is_enabled", "display_order")
    list_filter = ("is_enabled", "group")
    search_fields = ("name", "group")
