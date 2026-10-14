from django.contrib import admin

from apps.people.models import Person


@admin.register(Person)
class PersonAdmin(admin.ModelAdmin):
    list_display = ("employee_code", "full_name", "department", "is_active")
    list_filter = ("is_active", "department")
    search_fields = ("employee_code", "full_name")
