"""Tests for the management summary numbers (apps/events/report.py). Rows are created inside each test."""

from datetime import datetime, timedelta

from django.test import TestCase
from django.utils import timezone

from apps.cameras.models import Camera
from apps.events.models import Event
from apps.events.report import build_report, comparison, period_range, previous_range

ZONE = timezone.get_current_timezone()
NOW = datetime(2026, 3, 15, 14, 30, tzinfo=ZONE)


def make_event(minutes_ago=0, now=NOW, **fields):
    started = now - timedelta(minutes=minutes_ago)
    data = {
        "camera_name": "CAM-01",
        "module_key": "ppe",
        "event_type": "no_helmet",
        "severity": "critical",
        "started_at": started,
        "ended_at": started + timedelta(minutes=1),
    }
    data.update(fields)
    return Event.objects.create(**data)


class PeriodRangeTests(TestCase):
    def test_today_starts_at_local_midnight(self):
        start, end = period_range("today", NOW)
        assert start == datetime(2026, 3, 15, 0, 0, tzinfo=ZONE) and end == NOW

    def test_seven_days_include_today(self):
        start, _ = period_range("7d", NOW)
        assert start == datetime(2026, 3, 9, 0, 0, tzinfo=ZONE)

    def test_thirty_days(self):
        start, _ = period_range("30d", NOW)
        assert start == datetime(2026, 2, 14, 0, 0, tzinfo=ZONE)

    def test_bad_key_means_today(self):
        assert period_range("year", NOW) == period_range("today", NOW)

    def test_previous_range_ends_where_the_period_starts(self):
        start, end = period_range("7d", NOW)
        previous_start, previous_end = previous_range(start, end)
        assert previous_end == start and previous_end - previous_start == end - start


class ComparisonTests(TestCase):
    def test_directions(self):
        assert comparison(5, 0) == {"direction": "up", "diff": 5}
        assert comparison(2, 5) == {"direction": "down", "diff": 3}
        assert comparison(4, 4) == {"direction": "same", "diff": 0}


class ReportTests(TestCase):
    def test_cards_match_the_database(self):
        make_event(10)
        make_event(20, severity="warning", status="acknowledged")
        make_event(30, event_type="no_vest", ended_at=None)
        make_event(60 * 24 * 3)  # earlier than today: not in the period
        report = build_report("today", NOW)
        assert report["total"] == 3
        assert report["critical"] == 2
        assert report["not_acknowledged"] == 2
        assert report["going_on"] == 1
        assert dict((m.key, n) for m, n in report["module_cards"]) == {"ppe": 3}

    def test_going_on_is_not_limited_to_the_period(self):
        make_event(60 * 24 * 10, ended_at=None)
        assert build_report("today", NOW)["going_on"] == 1

    def test_comparison_with_previous_period(self):
        make_event(10)
        make_event(60 * 24)  # yesterday
        make_event(60 * 24 + 5)
        report = build_report("today", NOW)
        assert report["compare"] == {"direction": "down", "diff": 1}

    def test_hourly_chart_has_24_buckets_with_zeros(self):
        make_event(0)  # 14:30
        make_event(30)  # 14:00
        chart = build_report("today", NOW)["chart"]
        assert len(chart) == 24
        assert chart[14]["count"] == 2 and chart[14]["height"] == 100
        assert chart[3]["count"] == 0

    def test_daily_chart_puts_an_event_before_midnight_on_its_own_day(self):
        before_midnight = datetime(2026, 3, 14, 23, 59, tzinfo=ZONE)
        make_event(started_at=before_midnight, ended_at=None)
        chart = build_report("7d", NOW)["chart"]
        assert len(chart) == 7
        by_label = {b["label"]: b["count"] for b in chart}
        assert by_label["03-14"] == 1 and by_label["03-15"] == 0

    def test_empty_period_is_reported(self):
        report = build_report("30d", NOW)
        assert report["chart_empty"] and report["by_type"] == [] and report["attention"] == []

    def test_breakdown_by_type_is_sorted_and_linked(self):
        make_event(1)
        make_event(2)
        make_event(3, event_type="no_vest")
        rows = build_report("today", NOW)["by_type"]
        assert [r["count"] for r in rows] == [2, 1]
        assert "event_type=no_helmet" in rows[0]["url"] and "date_from=2026-03-15" in rows[0]["url"]
        assert rows[0]["share"] == 67

    def test_breakdown_by_camera_links_only_existing_cameras(self):
        camera = Camera.objects.create(name="CAM-01")
        make_event(1, camera=camera)
        make_event(2, camera=None, camera_name="CAM-GONE")
        rows = {r["label"]: r for r in build_report("today", NOW)["by_camera"]}
        assert f"camera={camera.pk}" in rows["CAM-01"]["url"]
        assert rows["CAM-GONE"]["url"] == ""

    def test_breakdown_collapses_the_tail_into_other(self):
        for i in range(12):
            make_event(i, camera_name=f"CAM-{i:02d}")
        rows = build_report("today", NOW)["by_camera"]
        assert len(rows) == 10 and rows[-1]["other"] and rows[-1]["count"] == 3

    def test_needs_attention_lists_only_open_events_newest_first_max_ten(self):
        make_event(5, status="acknowledged")
        for i in range(12):
            make_event(10 + i)
        attention = build_report("today", NOW)["attention"]
        assert len(attention) == 10
        assert attention[0]["time"] > attention[-1]["time"]

    def test_links_carry_the_period_dates(self):
        urls = build_report("7d", NOW)["urls"]
        assert "date_from=2026-03-09" in urls["print"] and "date_to=2026-03-15" in urls["print"]
        assert urls["print"].endswith("view=print")
        assert "status=open" in urls["not_acknowledged"]
