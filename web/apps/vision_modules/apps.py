"""Registry of vision modules (currently PPE). No database tables."""

from django.apps import AppConfig


class VisionModulesConfig(AppConfig):
    name = "apps.vision_modules"
    label = "vision_modules"
