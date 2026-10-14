"""Tests for the camera management pages and the source address rules."""

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import User
from apps.cameras.models import Camera
from apps.cameras.sources import is_valid_source, mask_source
from apps.core.engine_status import store_heartbeat

LOCMEM = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}


class SourceRulesTests(TestCase):
    def test_valid_sources(self):
        for value in (
            "rtsp://10.0.0.5/stream",
            "rtsps://u:p@host:322/x",
            "http://cam.local/video",
            "0",
            "C:\\videos\\a.mp4",
            "/data/a.mp4",
        ):
            self.assertTrue(is_valid_source(value), value)

    def test_invalid_sources(self):
        for value in ("", "   ", "ftp://host/x", "just text", "rtsp://"):
            self.assertFalse(is_valid_source(value), value)

    def test_password_is_masked(self):
        self.assertEqual(mask_source("rtsp://admin:Secret1@10.0.0.5:554/s"), "rtsp://admin:***@10.0.0.5:554/s")
        self.assertEqual(mask_source("rtsp://10.0.0.5/s"), "rtsp://10.0.0.5/s")
        self.assertEqual(mask_source("C:\\a.mp4"), "C:\\a.mp4")


@override_settings(CACHES=LOCMEM)
class CameraPagesTests(TestCase):
    def setUp(self):
        cache.clear()
        self.admin = User.objects.create_user("admin1", password="Str0ng-pass!", role="admin")
        self.operator = User.objects.create_user("operator1", password="Str0ng-pass!")

    def test_operator_is_refused(self):
        self.client.force_login(self.operator)
        for name in ("cameras:list", "cameras:create"):
            self.assertEqual(self.client.get(reverse(name)).status_code, 403)

    def test_admin_creates_edits_disables_deletes(self):
        self.client.force_login(self.admin)
        data = {
            "name": "CAM-01",
            "group": "Yard",
            "source_url": "rtsp://10.0.0.5/s",
            "modules": ["ppe"],
            "is_enabled": "on",
            "display_order": 1,
        }
        self.assertEqual(self.client.post(reverse("cameras:create"), data).status_code, 302)
        camera = Camera.objects.get()
        self.assertEqual(camera.modules, ["ppe"])

        data["name"] = "CAM-A"
        self.client.post(reverse("cameras:edit", args=[camera.pk]), data)
        camera.refresh_from_db()
        self.assertEqual(camera.name, "CAM-A")

        self.client.post(reverse("cameras:toggle", args=[camera.pk]))
        camera.refresh_from_db()
        self.assertFalse(camera.is_enabled)

        self.assertContains(self.client.get(reverse("cameras:delete", args=[camera.pk])), "CAM-A")
        self.client.post(reverse("cameras:delete", args=[camera.pk]))
        self.assertEqual(Camera.objects.count(), 0)

    def test_bad_source_and_missing_modules_are_rejected(self):
        self.client.force_login(self.admin)
        response = self.client.post(
            reverse("cameras:create"), {"name": "X", "source_url": "nonsense", "display_order": 0}
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("source_url", response.context["form"].errors)
        self.assertIn("modules", response.context["form"].errors)
        self.assertEqual(Camera.objects.count(), 0)

    def test_list_masks_password_and_shows_live_state(self):
        camera = Camera.objects.create(name="CAM-01", source_url="rtsp://admin:Secret1@10.0.0.5/s", modules=["ppe"])
        self.client.force_login(self.admin)
        page = self.client.get(reverse("cameras:list"))
        self.assertNotContains(page, "Secret1")
        self.assertContains(page, "admin:***@10.0.0.5")
        self.assertEqual(page.context["rows"][0]["state"], "unknown")  # engine silent

        store_heartbeat({"cameras": [{"id": camera.pk, "online": True, "fps": 14.6, "mode": "live"}]})
        row = self.client.get(reverse("cameras:list")).context["rows"][0]
        self.assertEqual((row["state"], row["fps"]), ("online", 14.6))

    def test_new_camera_reaches_the_engine_api(self):
        self.client.force_login(self.admin)
        self.client.post(
            reverse("cameras:create"),
            {"name": "CAM-09", "source_url": "0", "modules": ["ppe"], "is_enabled": "on", "display_order": 0},
        )
        with override_settings(ENGINE_API_TOKEN="t" * 40):
            data = self.client.get(
                reverse("cameras_api:engine_cameras"), HTTP_AUTHORIZATION="Bearer " + "t" * 40
            ).json()
        self.assertEqual([c["name"] for c in data["cameras"]], ["CAM-09"])
        self.assertEqual(data["cameras"][0]["modules"], ["ppe"])

    def test_engine_api_drops_unknown_module_keys(self):
        Camera.objects.create(name="CAM-01", source_url="0", modules=["retired", "ppe"])
        with override_settings(ENGINE_API_TOKEN="t" * 40):
            data = self.client.get(
                reverse("cameras_api:engine_cameras"), HTTP_AUTHORIZATION="Bearer " + "t" * 40
            ).json()
        self.assertEqual(data["cameras"][0]["modules"], ["ppe"])
