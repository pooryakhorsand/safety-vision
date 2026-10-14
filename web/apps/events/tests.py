"""Tests for the engine API, the management channel and maintenance."""

import shutil
import tempfile
import uuid
from datetime import timedelta
from pathlib import Path

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, TransactionTestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.cameras.models import Camera
from apps.events.maintenance import backup_database, purge_old_events
from apps.events.models import Event

TOKEN = "test-engine-token"
TEMP_DIR = tempfile.mkdtemp()


@override_settings(ENGINE_API_TOKEN=TOKEN, MEDIA_ROOT=Path(TEMP_DIR) / "media", BACKUP_DIR=Path(TEMP_DIR) / "backups")
class EventTestCase(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(TEMP_DIR, ignore_errors=True)

    def setUp(self):
        self.camera = Camera.objects.create(name="CAM-01")
        self.operator = User.objects.create_user("operator1", password="Str0ng-pass!")

    def post_event(self, token=TOKEN, **fields):
        return self.client.post(reverse("events_api:ingest"), fields, HTTP_AUTHORIZATION=f"Bearer {token}")

    def new_event_fields(self, **overrides):
        fields = {
            "uid": str(uuid.uuid4()),
            "camera_id": self.camera.pk,
            "module": "ppe",
            "event_type": "no_helmet",
            "started_at": timezone.now().isoformat(),
            "track_id": 3,
            "confidence": 0.91,
        }
        fields.update(overrides)
        return fields


class IngestApiTests(EventTestCase):
    def test_rejects_missing_or_wrong_token(self):
        self.assertEqual(self.post_event(token="wrong", **self.new_event_fields()).status_code, 401)
        self.assertEqual(self.client.post(reverse("events_api:ingest"), {}).status_code, 401)

    def test_creates_event_with_severity_from_type(self):
        response = self.post_event(**self.new_event_fields())
        self.assertEqual(response.status_code, 201)
        event = Event.objects.get()
        self.assertEqual(event.severity, "critical")
        self.assertEqual(event.camera_name, "CAM-01")
        self.assertTrue(event.is_ongoing)

    def test_same_uid_updates_instead_of_duplicating(self):
        fields = self.new_event_fields()
        self.post_event(**fields)
        response = self.post_event(uid=fields["uid"], ended_at=(timezone.now() + timedelta(minutes=2)).isoformat())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Event.objects.count(), 1)
        self.assertFalse(Event.objects.get().is_ongoing)

    def test_rejects_event_type_of_other_module(self):
        response = self.post_event(**self.new_event_fields(event_type="not_a_ppe_type"))
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Event.objects.count(), 0)

    def test_rejects_unknown_camera(self):
        self.assertEqual(self.post_event(**self.new_event_fields(camera_id=999)).status_code, 400)

    def test_accepts_json_body(self):
        response = self.client.post(
            reverse("events_api:ingest"),
            data=self.new_event_fields(extra={"zone": "deck"}),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {TOKEN}",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(Event.objects.get().extra, {"zone": "deck"})

    def test_snapshot_upload_and_protected_download(self):
        image = SimpleUploadedFile("frame.jpg", b"\xff\xd8\xff\xe0fake-jpeg", content_type="image/jpeg")
        self.post_event(**self.new_event_fields(snapshot=image))
        event = Event.objects.get()
        self.assertTrue(event.snapshot.name.endswith("_snapshot.jpg"))

        url = reverse("events:snapshot", args=[event.pk])
        self.assertEqual(self.client.get(url).status_code, 302)  # not signed in
        self.client.force_login(self.operator)
        self.assertEqual(self.client.get(url).status_code, 200)

    def test_engine_camera_list(self):
        response = self.client.get(reverse("cameras_api:engine_cameras"), HTTP_AUTHORIZATION=f"Bearer {TOKEN}")
        self.assertEqual(response.status_code, 200)
        camera = response.json()["cameras"][0]
        self.assertEqual(camera["name"], "CAM-01")
        self.assertEqual(camera["modules"], ["ppe"])


class ManagementChannelTests(EventTestCase):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.operator)
        now = timezone.now()
        self.helmet = Event.objects.create(
            camera=self.camera,
            camera_name="CAM-01",
            module_key="ppe",
            event_type="no_helmet",
            track_id=1,
            started_at=now - timedelta(hours=1),
            ended_at=now - timedelta(minutes=50),
        )
        self.vest = Event.objects.create(
            camera=self.camera,
            camera_name="CAM-01",
            module_key="ppe",
            event_type="no_vest",
            track_id=2,
            started_at=now - timedelta(days=3),
        )

    def test_list_filters_by_type_and_track(self):
        response = self.client.get(reverse("events:list"), {"event_type": "no_helmet"})
        self.assertEqual(list(response.context["page"].object_list), [self.helmet])
        response = self.client.get(reverse("events:list"), {"track_id": 2})
        self.assertEqual(list(response.context["page"].object_list), [self.vest])

    def test_event_of_a_removed_module_still_renders(self):
        old = Event.objects.create(
            camera=self.camera,
            camera_name="CAM-01",
            module_key="retired",
            event_type="something",
            started_at=timezone.now(),
        )
        self.assertEqual(old.module_name, "retired")
        self.assertEqual(old.type_name, "something")
        self.assertEqual(self.client.get(reverse("events:list")).status_code, 200)
        self.assertEqual(self.client.get(reverse("events:detail", args=[old.pk])).status_code, 200)
        self.assertEqual(self.client.get(reverse("events_api:summary")).status_code, 200)

    def test_list_filters_by_date(self):
        today = timezone.localdate().isoformat()
        response = self.client.get(reverse("events:list"), {"date_from": today})
        self.assertEqual(list(response.context["page"].object_list), [self.helmet])

    def test_acknowledge_records_who_and_when(self):
        self.client.post(reverse("events:acknowledge", args=[self.helmet.pk]), {"note": "Warned on site"})
        self.helmet.refresh_from_db()
        self.assertEqual(self.helmet.status, Event.Status.ACKNOWLEDGED)
        self.assertEqual(self.helmet.acknowledged_by, self.operator)
        self.assertEqual(self.helmet.note, "Warned on site")
        self.assertIsNotNone(self.helmet.acknowledged_at)

    def test_csv_export_respects_filters(self):
        response = self.client.get(reverse("events:list"), {"event_type": "no_vest", "export": "csv"})
        content = response.content.decode("utf-8-sig")
        self.assertEqual(response["Content-Type"], "text/csv; charset=utf-8")
        self.assertEqual(len(content.strip().splitlines()), 2)  # header + one event

    def test_print_view(self):
        response = self.client.get(reverse("events:list"), {"view": "print"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["total"], 2)

    def test_summary_counts_open_events(self):
        data = self.client.get(reverse("events_api:summary")).json()
        self.assertEqual(data["open_total"], 2)
        self.assertEqual(data["open_by_module"], {"ppe": 2})
        self.assertEqual(data["alarm_camera_ids"], [self.camera.pk])  # the vest event is ongoing
        self.assertEqual(len(data["latest"]), 2)


class MaintenanceTests(EventTestCase):
    def test_purge_deletes_old_events_and_files(self):
        old = Event(
            camera=self.camera,
            camera_name="CAM-01",
            module_key="ppe",
            event_type="no_vest",
            started_at=timezone.now() - timedelta(days=40),
        )
        old.snapshot.save("a.jpg", SimpleUploadedFile("a.jpg", b"jpeg"), save=False)
        old.save()
        file_path = Path(old.snapshot.path)
        Event.objects.create(
            camera=self.camera,
            camera_name="CAM-01",
            module_key="ppe",
            event_type="no_vest",
            started_at=timezone.now(),
        )
        self.assertEqual(purge_old_events(retention_days=30), 1)
        self.assertEqual(Event.objects.count(), 1)
        self.assertFalse(file_path.exists())


@override_settings(BACKUP_DIR=Path(TEMP_DIR) / "backups")
class BackupTests(TransactionTestCase):
    """Outside a test transaction: SQLite's online backup waits for open transactions."""

    def test_backup_keeps_newest_copies(self):
        backup_dir = Path(TEMP_DIR) / "backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        for name in ("db_20200101_000000.sqlite3", "db_20200102_000000.sqlite3"):
            (backup_dir / name).write_bytes(b"old")
        path = backup_database(keep=2)
        remaining = sorted(p.name for p in backup_dir.glob("db_*.sqlite3"))
        self.assertTrue(path.exists())
        self.assertEqual(len(remaining), 2)
        self.assertNotIn("db_20200101_000000.sqlite3", remaining)
