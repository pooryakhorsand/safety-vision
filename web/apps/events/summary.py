"""
Numbers for the live parts of the UI (navbar bell, sidebar counters,
overview cards, latest-events strip, red camera tiles).

Used by GET /api/events/summary/ and by the overview page.
"""

from django.db.models import Count
from django.urls import reverse
from django.utils import timezone

from apps.events.models import Event
from apps.vision_modules.registry import get_enabled_modules

LATEST_LIMIT = 8


def start_of_today():
    now = timezone.localtime()
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


def today_counts_by_module() -> dict[str, int]:
    rows = Event.objects.filter(started_at__gte=start_of_today()).values("module_key").annotate(total=Count("id"))
    counts = {module.key: 0 for module in get_enabled_modules()}
    counts.update({row["module_key"]: row["total"] for row in rows if row["module_key"] in counts})
    return counts


def build_summary(active_module: str = "") -> dict:
    open_events = Event.objects.filter(status=Event.Status.OPEN)

    open_by_module = {module.key: 0 for module in get_enabled_modules()}
    for row in open_events.values("module_key").annotate(total=Count("id")):
        if row["module_key"] in open_by_module:
            open_by_module[row["module_key"]] = row["total"]

    # Cameras with an ongoing, unacknowledged violation -> their tiles turn red.
    alarm_cameras = open_events.filter(ended_at__isnull=True)
    if active_module:
        alarm_cameras = alarm_cameras.filter(module_key=active_module)
    alarm_camera_ids = sorted({cid for cid in alarm_cameras.values_list("camera_id", flat=True) if cid})

    latest = [
        {
            "id": event.pk,
            "url": reverse("events:detail", args=[event.pk]),
            "time": timezone.localtime(event.started_at).strftime("%H:%M:%S"),
            "camera": event.camera_name,
            "module": event.module_name,
            "type": event.type_name,
            "severity": event.severity,
            "track_id": event.track_id,
            "is_open": event.is_open,
            "is_ongoing": event.is_ongoing,
        }
        for event in Event.objects.all()[:LATEST_LIMIT]
    ]

    return {
        "open_total": sum(open_by_module.values()),
        "open_by_module": open_by_module,
        "today_by_module": today_counts_by_module(),
        "alarm_camera_ids": alarm_camera_ids,
        "latest": latest,
    }
