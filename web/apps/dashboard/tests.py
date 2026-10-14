"""Tests for the main pages, module selection and language switching."""

from datetime import timedelta

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.cameras.models import Camera
from apps.events.models import Event


class LivePageTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("operator1", password="Str0ng-pass!")
        self.client.force_login(self.user)
        for i in range(1, 5):
            Camera.objects.create(name=f"CAM-{i:02d}", display_order=i)

    def test_grid_shows_every_enabled_camera(self):
        Camera.objects.create(name="CAM-OFF", is_enabled=False)
        response = self.client.get(reverse("dashboard:live"))
        self.assertEqual(len(response.context["cameras"]), 4)
        self.assertNotContains(response, "CAM-OFF")

    def test_default_module_is_first_enabled(self):
        response = self.client.get(reverse("dashboard:live"))
        self.assertEqual(response.context["active_module"].key, "ppe")

    def test_module_can_be_selected(self):
        response = self.client.get(reverse("dashboard:live") + "?module=ppe")
        self.assertEqual(response.context["active_module"].key, "ppe")

    def test_unknown_module_falls_back(self):
        response = self.client.get(reverse("dashboard:live") + "?module=nope")
        self.assertEqual(response.context["active_module"].key, "ppe")

    def test_camera_with_an_unknown_module_does_not_break_the_pages(self):
        Camera.objects.filter(name="CAM-01").update(modules=["retired"])
        live = self.client.get(reverse("dashboard:live"))
        self.assertEqual(live.status_code, 200)
        self.assertNotIn("CAM-01", [c.name for c in live.context["cameras"]])
        self.assertEqual(self.client.get(reverse("dashboard:settings")).status_code, 403)  # operator


class GridLayoutTests(TestCase):
    def test_layout_options_follow_camera_count(self):
        from apps.dashboard.views import grid_layout_options

        self.assertEqual(grid_layout_options(1), [1])
        self.assertEqual(grid_layout_options(2), [1, 2])
        self.assertEqual(grid_layout_options(3), [1, 2, 4])
        self.assertEqual(grid_layout_options(5), [1, 2, 4, 9])
        self.assertEqual(grid_layout_options(30), [1, 2, 4, 9, 16])

    def test_two_cameras_render_side_by_side(self):
        self.client.force_login(User.objects.create_user("u1", password="Str0ng-pass!"))
        Camera.objects.create(name="CAM-01")
        Camera.objects.create(name="CAM-02")
        response = self.client.get(reverse("dashboard:live"))
        self.assertContains(response, 'data-layout="2"')
        self.assertNotContains(response, 'data-layout="4"')


class LanguageTests(TestCase):
    def setUp(self):
        self.client.force_login(User.objects.create_user("u1", password="Str0ng-pass!"))

    def test_persian_is_right_to_left(self):
        self.client.post(reverse("set_language"), {"language": "fa"})
        response = self.client.get(reverse("dashboard:overview"))
        self.assertContains(response, 'dir="rtl"')

    def test_english_is_left_to_right(self):
        self.client.post(reverse("set_language"), {"language": "en"})
        response = self.client.get(reverse("dashboard:overview"))
        self.assertContains(response, 'dir="ltr"')


class SystemStatusApiTests(TestCase):
    def test_requires_login(self):
        response = self.client.get(reverse("core:system_status"))
        self.assertEqual(response.status_code, 302)

    def test_returns_engine_state(self):
        self.client.force_login(User.objects.create_user("u1", password="Str0ng-pass!"))
        data = self.client.get(reverse("core:system_status")).json()
        self.assertIn(data["engine"]["state"], ("online", "offline", "error"))


class OverviewPageTests(TestCase):
    def setUp(self):
        self.operator = User.objects.create_user("operator1", password="Str0ng-pass!")
        self.admin = User.objects.create_user("admin1", password="Str0ng-pass!", role="admin")
        self.url = reverse("dashboard:overview")

    def add_event(self, **fields):
        data = {"camera_name": "CAM-01", "module_key": "ppe", "event_type": "no_helmet", "started_at": timezone.now()}
        data.update(fields)
        return Event.objects.create(**data)

    def test_renders_for_operator_and_admin_with_no_events(self):
        for user in (self.operator, self.admin):
            self.client.force_login(user)
            response = self.client.get(self.url)
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, 'class="empty-note"', count=4)  # chart, two breakdowns, attention

    def test_requires_login(self):
        self.assertEqual(self.client.get(self.url).status_code, 302)

    def test_counts_and_period_links(self):
        self.client.force_login(self.operator)
        self.add_event(severity="critical")
        self.add_event(started_at=timezone.now() - timedelta(days=3))
        today = self.client.get(self.url).context["report"]
        week = self.client.get(self.url, {"period": "7d"}).context["report"]
        self.assertEqual((today["total"], week["total"]), (1, 2))
        self.assertEqual(self.client.get(self.url, {"period": "nonsense"}).context["report"]["period"], "today")

    def test_live_counter_attribute_only_for_today(self):
        self.client.force_login(self.operator)
        self.assertContains(self.client.get(self.url), "data-today-count")
        self.assertNotContains(self.client.get(self.url, {"period": "7d"}), "data-today-count")

    def test_needs_attention_links_to_the_event(self):
        self.client.force_login(self.operator)
        event = self.add_event()
        self.assertContains(self.client.get(self.url), reverse("events:detail", args=[event.pk]))

    def test_query_count_stays_small(self):
        self.client.force_login(self.operator)
        for i in range(15):
            self.add_event(camera_name=f"CAM-{i}")
        self.client.get(self.url)  # warm caches (profile, status)
        with CaptureQueriesContext(connection) as queries:
            self.client.get(self.url)
        # about 8 for the report, the rest is session, user and site settings
        self.assertLessEqual(len(queries), 14)
