"""Users, roles (admin / operator), login, logout and user management."""

from django.apps import AppConfig


class AccountsConfig(AppConfig):
    name = "apps.accounts"
    label = "accounts"
