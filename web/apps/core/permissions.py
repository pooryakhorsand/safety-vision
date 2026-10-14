"""
Access control helpers.

    @login_required          -> any signed-in user (admin or operator)
    @admin_required          -> admins only; operators get a 403 page
    @engine_token_required   -> machine-to-machine API calls from the engine
                                (header "Authorization: Bearer <ENGINE_API_TOKEN>")

Use these decorators on every view. Templates use {% if user.is_admin %}
only to hide links; the decorator is what actually protects the page.
"""

import hmac
from functools import wraps

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt


def admin_required(view_func):
    """Allow the view only for users with the admin role."""

    @login_required
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_admin:
            raise PermissionDenied
        return view_func(request, *args, **kwargs)

    return wrapper


def engine_token_required(view_func):
    """Allow the view only when the request carries the engine's shared token."""

    @csrf_exempt  # machine client, authenticated by token instead of cookie
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        expected = settings.ENGINE_API_TOKEN
        if not expected:
            return JsonResponse({"error": "ENGINE_API_TOKEN is not configured on the server."}, status=503)
        header = request.headers.get("Authorization", "")
        given = header[7:] if header.startswith("Bearer ") else ""
        if not hmac.compare_digest(given.encode(), expected.encode()):
            return JsonResponse({"error": "Invalid or missing engine token."}, status=401)
        return view_func(request, *args, **kwargs)

    return wrapper


__all__ = ["login_required", "admin_required", "engine_token_required"]
