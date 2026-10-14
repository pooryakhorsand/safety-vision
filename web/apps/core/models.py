"""Site settings chosen at first run (one row). They override the defaults in the profile."""

from django.db import models
from django.utils.translation import gettext_lazy as _


class SiteSettings(models.Model):
    site_name = models.CharField(_("site name"), max_length=80, blank=True)
    default_language = models.CharField(_("default language"), max_length=2, blank=True)

    class Meta:
        verbose_name = _("site settings")
        verbose_name_plural = _("site settings")

    @classmethod
    def current(cls):
        """The single settings row, or None before first-run setup."""
        return cls.objects.filter(pk=1).first()

    @classmethod
    def save_values(cls, site_name: str, default_language: str):
        cls.objects.update_or_create(pk=1, defaults={"site_name": site_name, "default_language": default_language})
