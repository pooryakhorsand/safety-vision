"""
Two small middlewares.

FirstRunMiddleware       no user exists yet -> every page goes to /setup/ (create the first administrator)
DefaultLanguageMiddleware  a visitor without a language choice gets the language picked at first run
"""

from django.conf import settings
from django.db import DatabaseError
from django.shortcuts import redirect
from django.urls import reverse

from apps.accounts.models import User
from apps.core.models import SiteSettings

# Paths that must keep working while no administrator exists.
OPEN_PREFIXES = ("/static/", "/i18n/", "/api/")


class FirstRunMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        self._setup_done = False  # once an administrator exists this never needs asking again

    def __call__(self, request):
        if not self._setup_done:
            try:
                self._setup_done = User.objects.exists()
            except DatabaseError:  # tables not created yet (migrate has not run)
                return self.get_response(request)
        if not self._setup_done:
            setup_url = reverse("setup")
            if request.path != setup_url and not request.path.startswith(OPEN_PREFIXES):
                return redirect(setup_url)
        return self.get_response(request)


class DefaultLanguageMiddleware:
    """Placed before LocaleMiddleware: fills the language cookie from the stored default when there is none."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if settings.LANGUAGE_COOKIE_NAME not in request.COOKIES:
            try:
                site = SiteSettings.current()
            except DatabaseError:
                site = None
            if site and site.default_language:
                request.COOKIES[settings.LANGUAGE_COOKIE_NAME] = site.default_language
        return self.get_response(request)
