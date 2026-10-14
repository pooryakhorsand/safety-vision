"""Shared building blocks: profile loader, permissions, template tags, system API."""

from django.apps import AppConfig


class CoreConfig(AppConfig):
    name = "apps.core"
    label = "core"
