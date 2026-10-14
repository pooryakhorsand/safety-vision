"""Tests for people, operator assignment, reopen/merge fields and the engine heartbeat."""

import json
import time
import uuid
from datetime import timedelta

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.cameras.models import Camera
from apps.events.models import Event
from apps.people.models import Person

TOKEN = "test-engine-token"
LOCMEM = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}


@override_settings(ENGINE_API_TOKEN=TOKEN, CACHES=LOCMEM)
class WebCase(TestCase):
    def setUp(self):
        cache.clear()
        self.camera = Camera.objects.create(name="CAM-01")
        self.admin = User.objects.create_user("admin1", password="Str0ng-pass!", role="admin")
        self.operator = User.objects.create_user("operator1", password="Str0ng-pass!")
        self.person = Person.objects.create(employee_code="E100", full_name="Ali Rezaei", department="Hull")

    def post_event(self, **fields):
        return self.client.post(reverse("events_api:ingest"), fields, HTTP_AUTHORIZATION=f"Bearer {TOKEN}")

    def make_event(self, **extra):
        fields = {
            "uid": str(uuid.uuid4()),
            "camera_id": self.camera.pk,
            "module": "ppe",
            "event_type": "no_helmet",
            "started_at": timezone.now().isoformat(),
        }
        fields.update(extra)
        self.post_event(**fields)
        return Event.objects.get(uid=fields["uid"])


class ReopenTests(WebCase):
    def test_empty_ended_at_reopens_and_counts(self):
        event = self.make_event()
        self.post_event(uid=str(event.uid), ended_at=timezone.now().isoformat())
        event.refresh_from_db()
        self.assertIsNotNone(event.ended_at)

        event.acknowledge(self.operator)
        self.post_event(uid=str(event.uid), ended_at="", occurrences=2, last_seen_at=timezone.now().isoformat())
        event.refresh_from_db()
        self.assertIsNone(event.ended_at)
        self.assertEqual(event.occurrences, 2)
        self.assertEqual(event.status, Event.Status.OPEN)
        self.assertIsNotNone(event.last_seen_at)

    def test_missing_ended_at_does_not_reopen(self):
        event = self.make_event()
        ended = timezone.now()
        self.post_event(uid=str(event.uid), ended_at=ended.isoformat())
        self.post_event(uid=str(event.uid), confidence=0.5)
        event.refresh_from_db()
        self.assertIsNotNone(event.ended_at)

    def test_json_null_reopens(self):
        event = self.make_event()
        self.post_event(uid=str(event.uid), ended_at=timezone.now().isoformat())
        response = self.client.post(
            reverse("events_api:ingest"),
            json.dumps({"uid": str(event.uid), "ended_at": None}),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {TOKEN}",
        )
        self.assertEqual(response.status_code, 200)
        event.refresh_from_db()
        self.assertIsNone(event.ended_at)

    def test_track_ids_are_unioned(self):
        event = self.make_event(extra=json.dumps({"track_ids": [3, 5]}))
        self.post_event(uid=str(event.uid), extra=json.dumps({"track_ids": [5, 9]}))
        event.refresh_from_db()
        self.assertEqual(event.extra["track_ids"], [3, 5, 9])

    def test_engine_cannot_set_person(self):
        event = self.make_event(person=self.person.pk)
        self.assertIsNone(event.person)


class AssignmentTests(WebCase):
    def test_operator_assigns_and_clears(self):
        event = self.make_event()
        self.client.force_login(self.operator)
        url = reverse("events:assign_person", args=[event.pk])
        self.client.post(url, {"person": self.person.label})
        event.refresh_from_db()
        self.assertEqual(event.person, self.person)
        self.assertEqual(event.person_assigned_by, self.operator)

        self.client.post(url, {"person": ""})
        event.refresh_from_db()
        self.assertIsNone(event.person)
        self.assertEqual(event.assignments.count(), 2)

    def test_code_only_and_unknown(self):
        event = self.make_event()
        self.client.force_login(self.operator)
        url = reverse("events:assign_person", args=[event.pk])
        self.client.post(url, {"person": "e100"})
        event.refresh_from_db()
        self.assertEqual(event.person, self.person)
        self.client.post(url, {"person": "nobody"})
        event.refresh_from_db()
        self.assertEqual(event.person, self.person)  # unchanged on a bad entry

    def test_requires_login(self):
        event = self.make_event()
        response = self.client.post(reverse("events:assign_person", args=[event.pk]), {"person": "E100"})
        self.assertEqual(response.status_code, 302)
        event.refresh_from_db()
        self.assertIsNone(event.person)

    def test_filter_and_csv(self):
        a, b = self.make_event(), self.make_event()
        a.assign_person(self.person, self.operator)
        self.client.force_login(self.operator)
        mine = self.client.get(reverse("events:list"), {"person": self.person.pk})
        self.assertEqual(list(mine.context["page"].object_list), [a])
        none = self.client.get(reverse("events:list"), {"person": "none"})
        self.assertEqual(list(none.context["page"].object_list), [b])
        csv = self.client.get(reverse("events:list"), {"export": "csv"}).content.decode("utf-8")
        self.assertIn("E100", csv)

    def test_detail_and_print_render(self):
        event = self.make_event()
        event.assign_person(self.person, self.operator)
        self.client.force_login(self.operator)
        self.assertContains(self.client.get(reverse("events:detail", args=[event.pk])), "E100")
        self.assertEqual(self.client.get(reverse("events:list"), {"view": "print"}).status_code, 200)


class PeoplePagesTests(WebCase):
    def test_list_search_and_inactive(self):
        Person.objects.create(employee_code="E200", full_name="Left Company", is_active=False)
        self.client.force_login(self.operator)
        page = self.client.get(reverse("people:list"))
        self.assertContains(page, "E100")
        self.assertNotContains(page, "E200")
        self.assertContains(self.client.get(reverse("people:list"), {"show": "all"}), "E200")
        self.assertNotContains(self.client.get(reverse("people:list"), {"q": "zzz"}), "E100")

    def test_only_admin_edits(self):
        self.client.force_login(self.operator)
        self.assertEqual(self.client.get(reverse("people:create")).status_code, 403)
        self.client.force_login(self.admin)
        response = self.client.post(
            reverse("people:create"),
            {
                "employee_code": "E300",
                "full_name": "New Person",
                "is_active": "on",
            },
        )
        self.assertEqual(response.status_code, 302)
        dup = self.client.post(reverse("people:create"), {"employee_code": "e300", "full_name": "X"})
        self.assertEqual(dup.status_code, 200)

    def test_detail_counts_last_30_days(self):
        recent = self.make_event(occurrences=3)
        recent.assign_person(self.person, self.operator)
        old = self.make_event(started_at=(timezone.now() - timedelta(days=60)).isoformat())
        old.assign_person(self.person, self.operator)
        self.client.force_login(self.operator)
        page = self.client.get(reverse("people:detail", args=[self.person.pk]))
        self.assertEqual(page.context["total_events"], 1)
        self.assertEqual(page.context["by_type"][0]["times"], 3)


class HeartbeatTests(WebCase):
    def beat(self, payload, token=TOKEN):
        return self.client.post(
            reverse("core:engine_heartbeat"),
            json.dumps(payload),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )

    def test_offline_without_heartbeat(self):
        self.client.force_login(self.operator)
        data = self.client.get(reverse("core:system_status")).json()
        self.assertEqual(data["engine"]["state"], "offline")

    def test_token_required(self):
        self.assertEqual(self.beat({}, token="bad").status_code, 401)

    def test_online_status(self):
        payload = {
            "engine_version": "0.1.0",
            "uptime_seconds": 90,
            "gpu": {"name": "GTX 1650", "memory_used_mb": 1000, "memory_total_mb": 4000},
            "cameras": [
                {"id": 1, "online": True, "fps": 20.0, "mode": "replay"},
                {"id": 2, "online": False, "fps": 0.0, "mode": "live"},
            ],
        }
        self.assertEqual(self.beat(payload).status_code, 200)
        self.client.force_login(self.operator)
        data = self.client.get(reverse("core:system_status")).json()
        self.assertEqual(data["engine"]["state"], "online")
        self.assertEqual(data["gpu"]["memory_percent"], 25)
        self.assertEqual(data["fps"], 20.0)
        self.assertEqual(
            data["cameras"],
            {
                "online": 1,
                "total": 2,
                "items": {
                    "1": {"online": True, "fps": 20.0, "mode": "replay"},
                    "2": {"online": False, "fps": 0.0, "mode": "live"},
                },
            },
        )

    def test_missing_models_show_as_error(self):
        self.beat(
            {
                "models_ok": False,
                "missing_models": [{"key": "detectors.equipment.weights", "path": "x.pt"}],
                "cameras": [],
            }
        )
        self.client.force_login(self.operator)
        engine = self.client.get(reverse("core:system_status")).json()["engine"]
        self.assertEqual(engine["state"], "error")
        self.assertEqual(engine["missing_models"][0]["path"], "x.pt")

    @override_settings(ENGINE_HEARTBEAT_TIMEOUT_SECONDS=0)
    def test_stale_heartbeat_is_offline(self):
        self.beat({"cameras": []})
        self.client.force_login(self.operator)
        time.sleep(0.01)
        self.assertEqual(self.client.get(reverse("core:system_status")).json()["engine"]["state"], "offline")

    def test_live_page_has_stream_url(self):
        self.client.force_login(self.operator)
        with override_settings(ENGINE_STREAM_URL="http://engine:8765/"):
            page = self.client.get(reverse("dashboard:live"))
        self.assertContains(page, 'data-stream-url="http://engine:8765"')
