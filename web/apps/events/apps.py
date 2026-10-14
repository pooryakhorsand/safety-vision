"""Events: violations reported by the engine, the management channel, acknowledge, export, retention."""

from django.apps import AppConfig


class EventsConfig(AppConfig):
    name = "apps.events"
    label = "events"

    def ready(self):
        from apps.events import signals  # noqa: F401  (connects file clean-up on delete)
