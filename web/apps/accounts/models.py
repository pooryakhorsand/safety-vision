"""
User model with a role.

Two roles for now:
    admin     -> everything, including users, cameras and settings
    operator  -> live view, overview and events (read-only)

A Django superuser (created with `createsuperuser`) is always an admin.
"""

from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils.translation import gettext_lazy as _


class User(AbstractUser):
    class Role(models.TextChoices):
        ADMIN = "admin", _("Administrator")
        OPERATOR = "operator", _("Operator")

    role = models.CharField(
        _("role"),
        max_length=20,
        choices=Role.choices,
        default=Role.OPERATOR,
    )

    class Meta:
        verbose_name = _("user")
        verbose_name_plural = _("users")
        ordering = ["username"]

    def save(self, *args, **kwargs):
        # Keep superusers and the admin role in sync.
        if self.is_superuser:
            self.role = self.Role.ADMIN
        super().save(*args, **kwargs)

    @property
    def is_admin(self) -> bool:
        return self.role == self.Role.ADMIN

    @property
    def display_name(self) -> str:
        return self.get_full_name() or self.username
