"""
Numbers for the management summary on the overview page.

Everything is read from the Event table with aggregate queries (nothing is loaded
event by event) and returned as plain data, so the view only renders it.

    build_report("7d")  ->  {"cards": ..., "chart": ..., "by_type": ..., "by_camera": ..., "attention": ...}
"""

from __future__ import annotations

from datetime import datetime, timedelta
from urllib.parse import urlencode

from django.db.models import Count, Q
from django.db.models.functions import TruncDate, TruncHour
from django.urls import reverse
from django.utils import timezone

from apps.events.models import Event
from apps.vision_modules.registry import get_any_module, get_enabled_modules

PERIODS = {"today": 0, "7d": 6, "30d": 29}  # key -> days before today that the period starts
DEFAULT_PERIOD = "today"
BREAKDOWN_LIMIT = 10
ATTENTION_LIMIT = 10


def clean_period(key: str) -> str:
    """Unknown values mean today."""
    return key if key in PERIODS else DEFAULT_PERIOD


def period_range(key: str, now: datetime) -> tuple[datetime, datetime]:
    """(start, end) in local time. The period starts at local midnight and ends now."""
    days_back = PERIODS[clean_period(key)]
    start = now.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=days_back)
    return start, now


def previous_range(start: datetime, end: datetime) -> tuple[datetime, datetime]:
    """The window of the same length that ends exactly where this one starts."""
    return start - (end - start), start


def list_url(start: datetime, end: datetime, **filters) -> str:
    """Link to the event list for the period, with extra filters (module, event_type, camera, status)."""
    params = {"date_from": start.date().isoformat(), "date_to": end.date().isoformat(), **filters}
    return f"{reverse('events:list')}?{urlencode(params)}"


def print_url(start: datetime, end: datetime) -> str:
    return f"{list_url(start, end)}&view=print"


def comparison(current: int, previous: int) -> dict:
    """How the period compares with the one before: direction is up, down or same."""
    diff = current - previous
    return {"direction": "up" if diff > 0 else "down" if diff < 0 else "same", "diff": abs(diff)}


def hourly_buckets(counts: dict[int, int]) -> list[dict]:
    """24 bars, one per local hour; labels only every 3rd hour so they do not overlap."""
    return [{"label": f"{h:02d}:00", "count": counts.get(h, 0), "show_label": h % 3 == 0} for h in range(24)]


def daily_buckets(counts: dict, start: datetime, end: datetime) -> list[dict]:
    """One bar per local day from start to end; labels every 5th day."""
    days = (end.date() - start.date()).days + 1
    result = []
    for i in range(days):
        day = start.date() + timedelta(days=i)
        result.append({"label": day.strftime("%m-%d"), "count": counts.get(day, 0), "show_label": i % 5 == 0})
    return result


def _with_shares(rows: list[dict], total: int) -> list[dict]:
    for row in rows:
        row["share"] = round(row["count"] * 100 / total) if total else 0
    return rows


def _limited(rows: list[dict], total: int) -> list[dict]:
    """Top rows plus one "Other" row (other=True, no link) for the rest."""
    rows = sorted(rows, key=lambda r: (-r["count"], r["label"]))
    if len(rows) > BREAKDOWN_LIMIT:
        rest = sum(r["count"] for r in rows[BREAKDOWN_LIMIT - 1 :])
        rows = rows[: BREAKDOWN_LIMIT - 1] + [{"label": "", "count": rest, "url": "", "other": True}]
    return _with_shares(rows, total)


def _type_label(module_key: str, event_type: str) -> str:
    module = get_any_module(module_key)
    if not module:
        return f"{module_key} · {event_type}"
    kind = module.get_event_type(event_type)
    return f"{module.name} · {kind.name if kind else event_type}"


def build_report(period_key: str = DEFAULT_PERIOD, now: datetime | None = None) -> dict:
    """All data for the overview page for one period."""
    period = clean_period(period_key)
    now = now or timezone.localtime()
    start, end = period_range(period, now)
    previous_start, previous_end = previous_range(start, end)
    zone = timezone.get_current_timezone()

    events = Event.objects.filter(started_at__gte=start, started_at__lte=end)

    totals = events.aggregate(
        total=Count("id"),
        critical=Count("id", filter=Q(severity=Event.Severity.CRITICAL)),
        not_acknowledged=Count("id", filter=Q(status=Event.Status.OPEN)),
    )
    previous_total = Event.objects.filter(started_at__gte=previous_start, started_at__lt=previous_end).count()
    going_on = Event.objects.filter(ended_at__isnull=True).count()
    total = totals["total"]

    by_module = {r["module_key"]: r["n"] for r in events.values("module_key").annotate(n=Count("id"))}

    # Chart: grouped by local hour (today) or local day.
    if period == "today":
        rows = events.annotate(b=TruncHour("started_at", tzinfo=zone)).values("b").annotate(n=Count("id"))
        chart = hourly_buckets({timezone.localtime(r["b"], zone).hour: r["n"] for r in rows})
    else:
        rows = events.annotate(b=TruncDate("started_at", tzinfo=zone)).values("b").annotate(n=Count("id"))
        chart = daily_buckets({r["b"]: r["n"] for r in rows}, start, end)
    peak = max((b["count"] for b in chart), default=0)
    for bar in chart:
        bar["height"] = round(bar["count"] * 100 / peak) if peak else 0

    type_rows = [
        {
            "label": _type_label(r["module_key"], r["event_type"]),
            "count": r["n"],
            "url": list_url(start, end, event_type=r["event_type"]),
        }
        for r in events.values("module_key", "event_type").annotate(n=Count("id"))
    ]
    camera_rows = [
        {
            "label": r["camera_name"],
            "count": r["n"],
            "url": list_url(start, end, camera=r["camera_id"]) if r["camera_id"] else "",
        }
        for r in events.values("camera_id", "camera_name").annotate(n=Count("id"))
    ]

    waiting = Event.objects.filter(status=Event.Status.OPEN).order_by("-started_at")[:ATTENTION_LIMIT]
    attention = [
        {
            "url": reverse("events:detail", args=[e.pk]),
            "time": timezone.localtime(e.started_at),
            "camera": e.camera_name,
            "type": e.type_name,
            "severity": e.severity,
            "severity_label": e.get_severity_display(),
            "ongoing": e.ended_at is None,
        }
        for e in waiting
    ]

    return {
        "period": period,
        "start": start,
        "end": end,
        "total": total,
        "critical": totals["critical"],
        "not_acknowledged": totals["not_acknowledged"],
        "going_on": going_on,
        "compare": comparison(total, previous_total),
        "module_cards": [(module, by_module.get(module.key, 0)) for module in get_enabled_modules()],
        "chart": chart,
        "chart_empty": total == 0,
        "chart_hourly": period == "today",
        "by_type": _limited(type_rows, total),
        "by_camera": _limited(camera_rows, total),
        "attention": attention,
        "urls": {
            "period_events": list_url(start, end),
            "not_acknowledged": list_url(start, end, status=Event.Status.OPEN),
            "open_all": f"{reverse('events:list')}?{urlencode({'status': Event.Status.OPEN})}",
            "print": print_url(start, end),
        },
    }
