"""
Camera management (admin only).

    camera_list     cameras with their live state, as reported by the engine
    camera_create / camera_edit
    camera_toggle   enable / disable
    camera_delete   confirmation page, then delete

Django never opens a camera stream: the state shown here comes from the engine's heartbeat.
"""

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from apps.cameras.forms import CameraForm
from apps.cameras.models import Camera
from apps.cameras.sources import mask_source
from apps.core.engine_status import read_status
from apps.core.permissions import admin_required


@admin_required
def camera_list(request):
    status = read_status()
    live = status["cameras"]["items"]
    engine_online = status["engine"]["state"] == "online"
    rows = []
    for camera in Camera.objects.all():
        info = live.get(str(camera.pk))
        if not camera.is_enabled:
            state = "disabled"
        elif not engine_online or info is None:
            state = "unknown"
        else:
            state = "online" if info["online"] else "offline"
        rows.append(
            {
                "camera": camera,
                "source": mask_source(camera.source_url),
                "state": state,
                "fps": info["fps"] if info and info["online"] else None,
            }
        )
    return render(request, "cameras/camera_list.html", {"rows": rows, "engine_online": engine_online})


@admin_required
def camera_create(request):
    form = CameraForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        camera = form.save()
        messages.success(request, _("“%(name)s” was added.") % {"name": camera.name})
        return redirect("cameras:list")
    return render(request, "cameras/camera_form.html", {"form": form, "camera": None})


@admin_required
def camera_edit(request, pk):
    camera = get_object_or_404(Camera, pk=pk)
    form = CameraForm(request.POST or None, instance=camera)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, _("Changes saved."))
        return redirect("cameras:list")
    return render(request, "cameras/camera_form.html", {"form": form, "camera": camera})


@admin_required
@require_POST
def camera_toggle(request, pk):
    camera = get_object_or_404(Camera, pk=pk)
    camera.is_enabled = not camera.is_enabled
    camera.save(update_fields=["is_enabled"])
    messages.success(request, _("Status updated."))
    return redirect("cameras:list")


@admin_required
def camera_delete(request, pk):
    camera = get_object_or_404(Camera, pk=pk)
    if request.method == "POST":
        name = camera.name
        camera.delete()  # events keep the camera name (the link is set to empty)
        messages.success(request, _("“%(name)s” was deleted.") % {"name": name})
        return redirect("cameras:list")
    return render(request, "cameras/camera_confirm_delete.html", {"camera": camera})
