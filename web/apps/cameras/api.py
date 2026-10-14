"""
GET /api/engine/cameras/  (engine token)

The engine reads its camera list from here, so cameras are configured in ONE
place (the web app) and the engine only needs the web address and the token.
"""

from django.http import JsonResponse
from django.views.decorators.http import require_GET

from apps.cameras.models import Camera
from apps.core.permissions import engine_token_required
from apps.vision_modules.registry import get_enabled_modules


@require_GET
@engine_token_required
def engine_camera_list(request):
    enabled_keys = [module.key for module in get_enabled_modules()]
    cameras = [
        {
            "id": camera.pk,
            "name": camera.name,
            "source_url": camera.source_url,
            "modules": [key for key in enabled_keys if camera.runs_module(key)],
        }
        for camera in Camera.objects.filter(is_enabled=True)
    ]
    return JsonResponse({"cameras": cameras})
