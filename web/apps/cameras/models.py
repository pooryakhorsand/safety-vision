"""
Camera sources.

The live grid is built from this table, so 2 cameras or 16 cameras is only
a matter of adding rows; no template changes.

Each camera also lists which vision modules run on it ("modules" field).
An empty list means: every module enabled in the site profile.
"""

from django.db import models
from django.utils.translation import gettext_lazy as _


class Camera(models.Model):
    name = models.CharField(_("name"), max_length=64, unique=True)  # e.g. "CAM-01"
    group = models.CharField(_("area"), max_length=64, blank=True)  # optional, e.g. "Main deck"
    source_url = models.CharField(
        _("source"),
        max_length=500,
        blank=True,
        help_text=_("RTSP URL, video file path or webcam index. Used by the engine."),
    )
    modules = models.JSONField(
        _("modules"),
        default=list,
        blank=True,
        help_text=_('Module keys that run on this camera, e.g. ["ppe"]. Empty = all enabled modules.'),
    )
    is_enabled = models.BooleanField(_("enabled"), default=True)
    display_order = models.PositiveIntegerField(_("display order"), default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("camera")
        verbose_name_plural = _("cameras")
        ordering = ["display_order", "name"]

    def __str__(self):
        return self.name

    def runs_module(self, module_key: str) -> bool:
        """True if the given module runs on this camera."""
        return not self.modules or module_key in self.modules
