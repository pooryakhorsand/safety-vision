"""Delete an event's snapshot / clip files when the event row is deleted (admin, purge, ...)."""

from django.db.models.signals import post_delete
from django.dispatch import receiver

from apps.events.models import Event


@receiver(post_delete, sender=Event)
def delete_event_files(sender, instance, **kwargs):
    instance.delete_files()
