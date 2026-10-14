"""
People = the employees an operator can assign to an event ("who is this?").

Deliberately small: a code, a name, a department. No photos and no biometric data:
the engine never sends names, and nothing here is used for recognition.
"""

from django.db import models
from django.utils.translation import gettext_lazy as _


class Person(models.Model):
    employee_code = models.CharField(_("employee code"), max_length=32, unique=True)
    full_name = models.CharField(_("full name"), max_length=120)
    department = models.CharField(_("department"), max_length=80, blank=True)
    is_active = models.BooleanField(_("active"), default=True)
    notes = models.TextField(_("notes"), blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("person")
        verbose_name_plural = _("people")
        ordering = ["full_name", "employee_code"]

    def __str__(self):
        return self.label

    @property
    def label(self) -> str:
        """How a person is shown in lists and in the "Who is this?" box."""
        return f"{self.employee_code} · {self.full_name}"
