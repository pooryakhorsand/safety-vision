"""Tests for start-up checks: secrets, data folder and version."""

import os
import subprocess
import sys
import tempfile
from pathlib import Path

from django.test import SimpleTestCase, TestCase

WEB_DIR = Path(__file__).resolve().parents[2]


def load_settings(**env):
    """Import the settings in a fresh process with the given environment; return (exit code, output)."""
    base = {k: v for k, v in os.environ.items() if not k.startswith(("DJANGO_", "ENGINE_", "APP_DATA", "DATA_DIR"))}
    code = "import web_config.settings as s; print(s.APP_VERSION, s.DATA_DIR, s.DATABASES['default']['NAME'])"
    result = subprocess.run(
        [sys.executable, "-c", code], cwd=WEB_DIR, env={**base, **env}, capture_output=True, text=True, timeout=60
    )
    return result.returncode, result.stdout + result.stderr


GOOD = "k" * 40


class StartupCheckTests(SimpleTestCase):
    def test_production_refuses_short_or_placeholder_secrets(self):
        with tempfile.TemporaryDirectory() as data:
            base = {"DJANGO_DEBUG": "false", "APP_DATA_DIR": data}
            for env in (
                {"DJANGO_SECRET_KEY": "short", "ENGINE_API_TOKEN": GOOD},
                {"DJANGO_SECRET_KEY": "change-me", "ENGINE_API_TOKEN": GOOD},
                {"DJANGO_SECRET_KEY": GOOD, "ENGINE_API_TOKEN": ""},
                {"DJANGO_SECRET_KEY": GOOD, "ENGINE_API_TOKEN": "dev-engine-token"},
            ):
                code, output = load_settings(**base, **env)
                self.assertNotEqual(code, 0, env)
                self.assertIn("at least 32 characters", output)

    def test_production_starts_with_good_secrets_and_uses_the_data_folder(self):
        with tempfile.TemporaryDirectory() as data:
            code, output = load_settings(
                DJANGO_DEBUG="false", DJANGO_SECRET_KEY=GOOD, ENGINE_API_TOKEN=GOOD + "x", APP_DATA_DIR=data
            )
            self.assertEqual(code, 0, output)
            version = (WEB_DIR.parent / "VERSION").read_text().strip()
            self.assertIn(version, output)
            self.assertIn(str(Path(data).resolve() / "db" / "db.sqlite3"), output)
            self.assertTrue((Path(data) / "logs").is_dir())

    def test_config_env_file_is_read_from_the_data_folder(self):
        with tempfile.TemporaryDirectory() as data:
            (Path(data) / "config").mkdir()
            (Path(data) / "config" / ".env").write_text(f"DJANGO_SECRET_KEY={GOOD}\nENGINE_API_TOKEN={GOOD}y\n")
            code, output = load_settings(DJANGO_DEBUG="false", APP_DATA_DIR=data)
            self.assertEqual(code, 0, output)


class FirstRunSetupTests(TestCase):
    """The setup page exists only while there is no user."""

    def setUp(self):
        from apps.core import middleware

        self.middleware = middleware

    def fresh_client(self):
        from django.test import Client

        return Client()

    def test_every_page_redirects_to_setup_when_there_is_no_user(self):
        # The middleware remembers "setup done" per process, so build a fresh handler.
        client = self.fresh_client()
        for url in ("/", "/dashboard/", "/accounts/login/", "/events/"):
            response = client.get(url)
            self.assertEqual((response.status_code, response["Location"]), (302, "/setup/"), url)

    def test_api_and_static_are_not_redirected(self):
        client = self.fresh_client()
        self.assertEqual(client.get("/api/system/status/").status_code, 302)  # login redirect, not setup
        self.assertNotEqual(client.get("/api/system/status/")["Location"], "/setup/")

    def test_setup_creates_the_first_admin_and_signs_in(self):
        from apps.accounts.models import User
        from apps.core.models import SiteSettings

        client = self.fresh_client()
        page = client.get("/setup/")
        self.assertEqual(page.status_code, 200)
        response = client.post(
            "/setup/",
            {
                "username": "boss",
                "password1": "Str0ng-pass!x",
                "password2": "Str0ng-pass!x",
                "site_name": "North Plant",
                "language": "en",
            },
        )
        self.assertRedirects(response, "/dashboard/overview/", fetch_redirect_response=False)
        user = User.objects.get(username="boss")
        self.assertTrue(user.is_admin and user.is_superuser)
        site = SiteSettings.current()
        self.assertEqual((site.site_name, site.default_language), ("North Plant", "en"))
        self.assertContains(client.get("/dashboard/overview/"), "North Plant")

    def test_setup_is_gone_after_the_first_admin(self):
        from apps.accounts.models import User

        User.objects.create_user("someone", password="Str0ng-pass!x")
        self.assertEqual(self.fresh_client().get("/setup/").status_code, 404)

    def test_default_language_applies_to_new_visitors(self):
        from apps.accounts.models import User
        from apps.core.models import SiteSettings

        User.objects.create_user("someone", password="Str0ng-pass!x")
        SiteSettings.save_values("Plant", "en")
        response = self.fresh_client().get("/accounts/login/")
        self.assertContains(response, 'dir="ltr"')


class SystemCheckTests(TestCase):
    def test_reads_the_launcher_file(self):
        import json
        import tempfile
        from pathlib import Path

        from django.test import override_settings

        from apps.accounts.models import User
        from apps.core.system_check import read_system_check

        with tempfile.TemporaryDirectory() as data:
            with override_settings(DATA_DIR=Path(data)):
                self.assertFalse(read_system_check()["available"])
                (Path(data) / "config").mkdir()
                (Path(data) / "config" / "system_check.json").write_text(
                    json.dumps(
                        {
                            "checked_at": "2026-01-01T10:00:00",
                            "gpu": {"name": "GTX 1650", "driver": "552.12", "memory_mb": 4096},
                            "cuda_available": True,
                            "disk": {"free_gb": 100.5},
                            "models": [{"key": "detectors.equipment.weights", "path": "x/ppe.pt", "found": False}],
                        }
                    )
                )
                check = read_system_check()
                self.assertTrue(check["available"])
                self.assertEqual(len(check["missing_models"]), 1)

                admin = User.objects.create_user("a", password="Str0ng-pass!x", role="admin")
                self.client.force_login(admin)
                page = self.client.get("/dashboard/settings/")
                self.assertContains(page, "GTX 1650")
                self.assertContains(page, "x/ppe.pt")
