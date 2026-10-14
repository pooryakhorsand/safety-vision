"""
Root URL map. Each app owns its own urls.py; this file only connects them.

    /                     -> redirect to the overview page
    /setup/               -> first-run setup, only while there is no user (apps.core)
    /accounts/...         -> login, logout, user management     (apps.accounts)
    /dashboard/...        -> overview, live view, settings      (apps.dashboard)
    /cameras/...          -> camera management (admin)           (apps.cameras)
    /events/...           -> management channel                 (apps.events)
    /people/...           -> employees an operator can assign   (apps.people)
    /api/...              -> JSON endpoints
        system/status/        status bar                         (apps.core)
        events/               engine sends events (token)        (apps.events)
        events/summary/       live counters for the UI           (apps.events)
        engine/cameras/       engine reads its camera list (token) (apps.cameras)
    /i18n/setlang/        -> language switch (Django built-in)
    /system-admin/        -> Django admin, superusers only
"""

from django.contrib import admin
from django.urls import include, path
from django.views.generic import RedirectView

urlpatterns = [
    path("", RedirectView.as_view(pattern_name="dashboard:overview", permanent=False)),
    path("", include("apps.core.page_urls")),
    path("accounts/", include("apps.accounts.urls")),
    path("dashboard/", include("apps.dashboard.urls")),
    path("cameras/", include("apps.cameras.page_urls")),
    path("events/", include("apps.events.urls")),
    path("people/", include("apps.people.urls")),
    path("api/", include("apps.core.urls")),
    path("api/", include("apps.events.api_urls")),
    path("api/", include("apps.cameras.urls")),
    path("i18n/", include("django.conf.urls.i18n")),
    path("system-admin/", admin.site.urls),
]
