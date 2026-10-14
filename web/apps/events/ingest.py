"""
Receiving events from the engine.

The engine sends the SAME uid twice for one violation:
    1. when it starts   -> uid, camera_id, module, event_type, started_at, (snapshot)
    2. when it ends     -> uid, ended_at  (plus anything that changed)
The first call creates the row, later calls update it. Sending the same
call again is harmless (idempotent), so the engine can retry safely.

Fields (form-data or JSON):
    uid          required  UUID chosen by the engine
    camera_id    required on create   id from GET /api/engine/cameras/
    module       required on create   e.g. "ppe"
    event_type   required on create   e.g. "no_helmet" (must belong to the module)
    started_at   required on create   ISO 8601, e.g. 2026-10-12T10:02:10+03:30
    ended_at     optional  ISO 8601. Sent as null / "" on an existing event it
                 REOPENS the event (the same person violated again)
    occurrences  optional  integer >= 1, how many times it happened (merged repeats)
    last_seen_at optional  ISO 8601, last time the violation was seen
    track_id     optional  integer
    confidence   optional  0..1
    severity     optional  info | warning | critical (default: from the event type)
    extra        optional  JSON object
    snapshot     optional  image file (form-data only)
"""

import json

from django import forms
from django.db import transaction

from apps.cameras.models import Camera
from apps.events.models import Event
from apps.vision_modules.registry import get_module

CREATE_FIELDS = ("camera_id", "module", "event_type", "started_at")
ALLOWED_SNAPSHOT_TYPES = {"image/jpeg", "image/png", "image/webp"}


class EventIngestForm(forms.Form):
    uid = forms.UUIDField()
    camera_id = forms.IntegerField(required=False, min_value=1)
    module = forms.CharField(required=False, max_length=32)
    event_type = forms.CharField(required=False, max_length=48)
    started_at = forms.DateTimeField(required=False)
    ended_at = forms.DateTimeField(required=False)
    occurrences = forms.IntegerField(required=False, min_value=1)
    last_seen_at = forms.DateTimeField(required=False)
    track_id = forms.IntegerField(required=False, min_value=0)
    confidence = forms.FloatField(required=False, min_value=0, max_value=1)
    severity = forms.ChoiceField(required=False, choices=Event.Severity.choices)
    extra = forms.JSONField(required=False)
    snapshot = forms.FileField(required=False)

    def clean_snapshot(self):
        snapshot = self.cleaned_data.get("snapshot")
        if snapshot and snapshot.content_type not in ALLOWED_SNAPSHOT_TYPES:
            raise forms.ValidationError("Snapshot must be JPEG, PNG or WebP.")
        return snapshot

    def clean_extra(self):
        extra = self.cleaned_data.get("extra")
        if extra in (None, ""):
            return None
        if not isinstance(extra, dict):
            raise forms.ValidationError("extra must be a JSON object.")
        return extra

    def clean(self):
        data = super().clean()
        started, ended = data.get("started_at"), data.get("ended_at")
        if started and ended and ended < started:
            self.add_error("ended_at", "ended_at is before started_at.")
        return data


def parse_request_data(request):
    """Accept both multipart form-data (with a snapshot) and plain JSON."""
    if request.content_type == "application/json":
        try:
            body = json.loads(request.body or b"{}")
        except json.JSONDecodeError as error:
            raise ValueError(f"Invalid JSON: {error}") from None
        if not isinstance(body, dict):
            raise ValueError("JSON body must be an object.")
        if isinstance(body.get("extra"), dict):
            body["extra"] = json.dumps(body["extra"])
        return body, {}
    return request.POST, request.FILES


def wants_reopen(data) -> bool:
    """True when the request contains ended_at but empty (null / "")."""
    return "ended_at" in data and data.get("ended_at") in (None, "")


@transaction.atomic
def save_event(data: dict, reopen: bool = False) -> tuple[Event, bool]:
    """
    Create or update an event from validated form data.
    reopen=True clears ended_at (see wants_reopen).
    Returns (event, created). Raises forms.ValidationError on bad input.
    """
    event = Event.objects.select_for_update().filter(uid=data["uid"]).first()
    created = event is None

    if created:
        missing = [name for name in CREATE_FIELDS if not data.get(name)]
        if missing:
            raise forms.ValidationError(f"Missing fields for a new event: {', '.join(missing)}")

        module = get_module(data["module"])
        if module is None:
            raise forms.ValidationError(f"Module '{data['module']}' is not enabled on this site.")
        event_type = module.get_event_type(data["event_type"])
        if event_type is None:
            raise forms.ValidationError(f"Event type '{data['event_type']}' does not belong to module '{module.key}'.")
        camera = Camera.objects.filter(pk=data["camera_id"]).first()
        if camera is None:
            raise forms.ValidationError(f"Camera {data['camera_id']} does not exist.")

        event = Event(
            uid=data["uid"],
            camera=camera,
            camera_name=camera.name,
            module_key=module.key,
            event_type=event_type.key,
            severity=data.get("severity") or event_type.severity,
            started_at=data["started_at"],
        )

    # Fields that may be set on create or updated later.
    for name in ("ended_at", "track_id", "confidence", "occurrences", "last_seen_at"):
        if data.get(name) is not None:
            setattr(event, name, data[name])
    if reopen and not created and not data.get("ended_at"):
        event.ended_at = None
        if event.status == Event.Status.ACKNOWLEDGED:
            # A new violation after the operator handled the old one needs attention again.
            event.status = Event.Status.OPEN
    if data.get("severity") and not created:
        event.severity = data["severity"]
    if data.get("extra"):
        merged = {**event.extra, **data["extra"]}
        old_ids, new_ids = event.extra.get("track_ids"), data["extra"].get("track_ids")
        if isinstance(old_ids, list) and isinstance(new_ids, list):
            merged["track_ids"] = sorted(set(old_ids) | set(new_ids))
        event.extra = merged
    if event.ended_at and event.ended_at < event.started_at:
        raise forms.ValidationError("ended_at is before started_at.")

    snapshot = data.get("snapshot")
    if snapshot:
        if event.snapshot:
            event.snapshot.storage.delete(event.snapshot.name)
        event.snapshot.save(snapshot.name, snapshot, save=False)

    event.save()
    return event, created
