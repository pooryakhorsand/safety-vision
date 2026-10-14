"""
JSON API for events.

    POST /api/events/           engine -> web   create or update one event   (engine token)
    GET  /api/events/summary/   browser -> web  live counters for the UI     (signed-in user)
"""

from django import forms
from django.http import JsonResponse
from django.views.decorators.http import require_GET, require_POST

from apps.core.permissions import engine_token_required, login_required
from apps.events.ingest import EventIngestForm, parse_request_data, save_event, wants_reopen
from apps.events.summary import build_summary


@require_POST
@engine_token_required
def ingest_event(request):
    try:
        data, files = parse_request_data(request)
    except ValueError as error:
        return JsonResponse({"error": str(error)}, status=400)

    form = EventIngestForm(data, files)
    if not form.is_valid():
        return JsonResponse({"error": "Invalid data.", "fields": form.errors.get_json_data()}, status=400)

    try:
        event, created = save_event(form.cleaned_data, reopen=wants_reopen(data))
    except forms.ValidationError as error:
        return JsonResponse({"error": " ".join(error.messages)}, status=400)

    return JsonResponse(
        {"id": event.pk, "uid": str(event.uid), "created": created, "status": event.status},
        status=201 if created else 200,
    )


@require_GET
@login_required
def events_summary(request):
    return JsonResponse(build_summary(active_module=request.GET.get("module", "")))
