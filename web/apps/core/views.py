"""
Small JSON endpoints used by the front-end JavaScript and by the engine.

GET  /api/system/status/     -> polled by the status bar every few seconds (signed-in user)
POST /api/engine/heartbeat/  -> the engine reports its state (engine token)

The state comes from the engine's last heartbeat (see engine_status.py);
no heartbeat for ENGINE_HEARTBEAT_TIMEOUT_SECONDS means "offline".
"""

import json

from django.http import JsonResponse
from django.views.decorators.http import require_POST

from apps.core.engine_status import read_status, store_heartbeat
from apps.core.permissions import engine_token_required, login_required


@login_required
def system_status(request):
    return JsonResponse(read_status())


@require_POST
@engine_token_required
def engine_heartbeat(request):
    try:
        payload = json.loads(request.body or b"{}")
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON."}, status=400)
    if not isinstance(payload, dict):
        return JsonResponse({"error": "JSON body must be an object."}, status=400)
    store_heartbeat(payload)
    return JsonResponse({"ok": True})
