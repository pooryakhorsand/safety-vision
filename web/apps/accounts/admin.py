"""Django admin registration (for superusers at /system-admin/)."""

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from apps.accounts.models import User


@admin.register(User)
class AppUserAdmin(UserAdmin):
    list_display = ("username", "first_name", "last_name", "role", "is_active", "last_login")
    list_filter = ("role", "is_active")
    fieldsets = UserAdmin.fieldsets + (("Role", {"fields": ("role",)}),)
    add_fieldsets = UserAdmin.add_fieldsets + (("Role", {"fields": ("role",)}),)
