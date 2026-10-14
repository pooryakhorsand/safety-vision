from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class PeopleConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.people"
    verbose_name = _("People")
