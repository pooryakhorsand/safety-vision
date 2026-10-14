"""Tests for login and role-based access."""

from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import User


class RoleAccessTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user("admin1", password="Str0ng-pass!", role=User.Role.ADMIN)
        self.operator = User.objects.create_user("operator1", password="Str0ng-pass!")

    def test_new_user_is_operator_by_default(self):
        self.assertEqual(self.operator.role, User.Role.OPERATOR)
        self.assertFalse(self.operator.is_admin)

    def test_superuser_is_always_admin(self):
        root = User.objects.create_superuser("root", password="Str0ng-pass!")
        self.assertTrue(root.is_admin)

    def test_login_page_shows_branding(self):
        # Django's LoginView adds its own "site" variable; branding must not clash with it.
        response = self.client.get(reverse("accounts:login"), HTTP_ACCEPT_LANGUAGE="en")
        self.assertContains(response, "Safety Vision")
        self.assertContains(response, "--accent: #")

    def test_anonymous_is_sent_to_login(self):
        response = self.client.get(reverse("dashboard:live"))
        self.assertRedirects(response, f"{reverse('accounts:login')}?next={reverse('dashboard:live')}")

    def test_operator_cannot_open_admin_pages(self):
        self.client.force_login(self.operator)
        self.assertEqual(self.client.get(reverse("accounts:user_list")).status_code, 403)
        self.assertEqual(self.client.get(reverse("dashboard:settings")).status_code, 403)

    def test_operator_can_open_operator_pages(self):
        self.client.force_login(self.operator)
        for name in ("dashboard:overview", "dashboard:live", "events:list"):
            self.assertEqual(self.client.get(reverse(name)).status_code, 200, name)

    def test_admin_can_create_user(self):
        self.client.force_login(self.admin)
        response = self.client.post(
            reverse("accounts:user_create"),
            {"username": "op2", "role": "operator", "password1": "An0ther-pass!", "password2": "An0ther-pass!"},
        )
        self.assertRedirects(response, reverse("accounts:user_list"))
        self.assertTrue(User.objects.filter(username="op2").exists())

    def test_admin_cannot_disable_self(self):
        self.client.force_login(self.admin)
        self.client.post(reverse("accounts:user_toggle_active", args=[self.admin.pk]))
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.is_active)
