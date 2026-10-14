"""
Event = one violation over a period of time, e.g.
    "Track #3 on CAM-01 had no helmet from 10:02:10 to 10:17:45"

Not one row per frame: the engine opens an event when a violation becomes
stable, then updates the same row (same uid) when it ends.

Snapshot / clip files live on disk under MEDIA_ROOT; the row stores the path.
"""

import uuid
from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.vision_modules.registry import get_any_module


def _event_file_path(instance, filename, role):
    """events/2026/10/12/<uid>_<role>.<ext>  (one folder per day, easy to clean up)"""
    extension = filename.rsplit(".", 1)[-1].lower() if "." in filename else "bin"
    day = (instance.started_at or timezone.now()).strftime("%Y/%m/%d")
    return f"events/{day}/{instance.uid}_{role}.{extension}"


def snapshot_path(instance, filename):
    return _event_file_path(instance, filename, "snapshot")


def clip_path(instance, filename):
    return _event_file_path(instance, filename, "clip")


class Event(models.Model):
    class Severity(models.TextChoices):
        INFO = "info", _("Info")
        WARNING = "warning", _("Warning")
        CRITICAL = "critical", _("Critical")

    class Status(models.TextChoices):
        OPEN = "open", _("Open")
        ACKNOWLEDGED = "acknowledged", _("Acknowledged")

    # --- Identity (set by the engine) ---
    uid = models.UUIDField(_("event ID"), unique=True, default=uuid.uuid4, editable=False)

    # --- What and where ---
    camera = models.ForeignKey(
        "cameras.Camera",
        verbose_name=_("camera"),
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="events",
    )
    camera_name = models.CharField(_("camera name"), max_length=64)  # kept if the camera is deleted later
    module_key = models.CharField(_("module"), max_length=32)  # "ppe"
    event_type = models.CharField(_("event type"), max_length=48)  # "no_helmet", ...
    severity = models.CharField(_("severity"), max_length=16, choices=Severity.choices, default=Severity.WARNING)
    track_id = models.PositiveIntegerField(_("track ID"), null=True, blank=True)  # person ID from the tracker
    confidence = models.FloatField(_("confidence"), null=True, blank=True)  # 0..1

    # --- When ---
    started_at = models.DateTimeField(_("started at"))
    ended_at = models.DateTimeField(_("ended at"), null=True, blank=True)  # empty = still going on

    # How many separate times the same person repeated this violation inside the
    # merge window (the engine reopens the same event instead of creating new ones).
    occurrences = models.PositiveIntegerField(_("occurrences"), default=1)
    last_seen_at = models.DateTimeField(_("last seen at"), null=True, blank=True)

    # --- Evidence (files on disk) ---
    snapshot = models.FileField(_("snapshot"), upload_to=snapshot_path, blank=True)
    clip = models.FileField(_("clip"), upload_to=clip_path, blank=True)

    # --- Operator handling ---
    # Who is this? Only an operator sets it; the engine API can never do so.
    person = models.ForeignKey(
        "people.Person",
        verbose_name=_("person"),
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="events",
    )
    person_assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("assigned by"),
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    person_assigned_at = models.DateTimeField(_("assigned at"), null=True, blank=True)
    status = models.CharField(_("status"), max_length=16, choices=Status.choices, default=Status.OPEN)
    acknowledged_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("acknowledged by"),
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="acknowledged_events",
    )
    acknowledged_at = models.DateTimeField(_("acknowledged at"), null=True, blank=True)
    note = models.TextField(_("note"), blank=True)

    # Anything else the engine wants to keep (bounding box, zone name, ...).
    extra = models.JSONField(_("extra data"), default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("event")
        verbose_name_plural = _("events")
        ordering = ["-started_at"]
        indexes = [
            # One index per common filter in the management channel.
            models.Index(fields=["-started_at"], name="event_started_idx"),
            models.Index(fields=["module_key", "-started_at"], name="event_module_idx"),
            models.Index(fields=["camera", "-started_at"], name="event_camera_idx"),
            models.Index(fields=["status", "-started_at"], name="event_status_idx"),
            models.Index(fields=["person", "-started_at"], name="event_person_idx"),
        ]

    def __str__(self):
        return f"{self.camera_name} · {self.event_type} · {self.started_at:%Y-%m-%d %H:%M}"

    # --- Display helpers -------------------------------------------------------
    @property
    def module(self):
        return get_any_module(self.module_key)

    @property
    def module_name(self) -> str:
        return str(self.module.name) if self.module else self.module_key

    @property
    def type_name(self) -> str:
        event_type = self.module.get_event_type(self.event_type) if self.module else None
        return str(event_type.name) if event_type else self.event_type

    @property
    def is_ongoing(self) -> bool:
        return self.ended_at is None

    @property
    def duration(self) -> timedelta:
        return (self.ended_at or timezone.now()) - self.started_at

    @property
    def is_open(self) -> bool:
        return self.status == self.Status.OPEN

    # --- Actions ------------------------------------------------------------------
    def acknowledge(self, user, note: str = ""):
        self.status = self.Status.ACKNOWLEDGED
        self.acknowledged_by = user
        self.acknowledged_at = timezone.now()
        if note:
            self.note = note
        self.save(update_fields=["status", "acknowledged_by", "acknowledged_at", "note", "updated_at"])

    def assign_person(self, person, user):
        """Set (or clear, with person=None) who this is, and keep a history row."""
        previous = self.person
        if previous == person:
            return False
        self.person = person
        self.person_assigned_by = user if person else None
        self.person_assigned_at = timezone.now() if person else None
        self.save(update_fields=["person", "person_assigned_by", "person_assigned_at", "updated_at"])
        EventAssignment.objects.create(event=self, changed_by=user, from_person=previous, to_person=person)
        return True

    def delete_files(self):
        for field in (self.snapshot, self.clip):
            if field:
                field.storage.delete(field.name)


class EventAssignment(models.Model):
    """History of "who is this?" changes, so a wrong assignment can be traced."""

    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="assignments")
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    changed_at = models.DateTimeField(auto_now_add=True)
    from_person = models.ForeignKey("people.Person", on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    to_person = models.ForeignKey("people.Person", on_delete=models.SET_NULL, null=True, blank=True, related_name="+")

    class Meta:
        ordering = ["-changed_at", "-id"]
