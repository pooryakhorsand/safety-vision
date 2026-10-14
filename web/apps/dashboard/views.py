"""
Main operator pages. (The management channel lives in apps/events.)

    overview   -> management summary for today / 7 / 30 days     (all users)
    live       -> camera grid with the module sidebar           (all users)
    settings   -> system configuration hub                      (admin only)

Django only DISPLAYS. All video processing happens in the separate engine
process (engine/ folder, its own environment); Django never touches frames.
"""

from django.conf import settings
from django.shortcuts import render
from django.utils.translation import gettext as _

from apps.cameras.models import Camera
from apps.core.engine_status import read_status
from apps.core.permissions import admin_required, login_required
from apps.core.system_check import read_system_check
from apps.events.report import build_report
from apps.vision_modules.registry import ALL_MODULES, get_enabled_modules, get_module

# Tiles per page the operator can choose from.
GRID_LAYOUTS = (1, 2, 4, 9, 16)


def grid_layout_options(camera_count: int) -> list[int]:
    """
    Layouts that make sense for this many cameras.

    2 cameras  -> [1, 2]          (no 4/9/16 with empty tiles)
    5 cameras  -> [1, 2, 4, 9]
    20 cameras -> [1, 2, 4, 9, 16] (paging handles the rest)
    """
    options = []
    for size in GRID_LAYOUTS:
        options.append(size)
        if size >= camera_count:
            break
    return options


@login_required
def overview(request):
    report = build_report(request.GET.get("period", ""))
    context = {
        "report": report,
        "periods": [("today", _("Today")), ("7d", _("7 days")), ("30d", _("30 days"))],
        "camera_count": Camera.objects.filter(is_enabled=True).count(),
        "cameras_online": read_status()["cameras"]["online"],
    }
    return render(request, "dashboard/overview.html", context)


@login_required
def live(request):
    modules = get_enabled_modules()
    # ?module=ppe selects a module; default is the first enabled one.
    active_module = get_module(request.GET.get("module", "")) or (modules[0] if modules else None)

    cameras = list(Camera.objects.filter(is_enabled=True))
    if active_module:
        cameras = [camera for camera in cameras if camera.runs_module(active_module.key)]

    layout_options = grid_layout_options(len(cameras))
    context = {
        "cameras": cameras,
        "active_module": active_module,
        "layout_options": layout_options,
        "default_layout": layout_options[-1],  # smallest layout that shows every camera
        "stream_url": settings.ENGINE_STREAM_URL.rstrip("/"),
    }
    return render(request, "dashboard/live.html", context)


@admin_required
def settings_home(request):
    enabled = get_enabled_modules()
    enabled_keys = {m.key for m in enabled}
    context = {
        "all_modules": [(module, module.key in enabled_keys) for module in ALL_MODULES.values()],
        # (camera, [modules running on it]) for the cameras table
        "camera_rows": [(camera, [m for m in enabled if camera.runs_module(m.key)]) for camera in Camera.objects.all()],
    }
    context["check"] = read_system_check()
    return render(request, "dashboard/settings.html", context)
