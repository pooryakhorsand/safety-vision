"""
Management channel pages (all signed-in users: admin and operator).

    event_list         table with filters + paging
                       ?export=csv  -> CSV file of the filtered events
                       ?view=print  -> printable report (browser "Save as PDF")
    event_detail       one event: snapshot, times, acknowledge form
    event_acknowledge  POST: operator confirms they have seen the alarm
    event_assign_person POST: operator says who the person is
    event_snapshot     serves the snapshot file to signed-in users only
"""

from django.contrib import messages
from django.core.paginator import Paginator
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from apps.core.permissions import login_required
from apps.events.export import events_to_csv
from apps.events.filters import EventFilterForm
from apps.events.models import Event
from apps.people.models import Person

PAGE_SIZE = 25
PRINT_LIMIT = 1000


@login_required
def event_list(request):
    form = EventFilterForm(request.GET or None)
    events = form.apply(Event.objects.select_related("acknowledged_by", "person"))

    if request.GET.get("export") == "csv":
        return events_to_csv(events)

    if request.GET.get("view") == "print":
        return render(
            request,
            "events/event_print.html",
            {
                "events": events[:PRINT_LIMIT],
                "total": events.count(),
                "limit": PRINT_LIMIT,
                "form": form,
                "printed_at": timezone.localtime(),
            },
        )

    page = Paginator(events, PAGE_SIZE).get_page(request.GET.get("page"))
    query = request.GET.copy()
    query.pop("page", None)
    return render(
        request,
        "events/event_list.html",
        {
            "form": form,
            "page": page,
            "query": query.urlencode(),  # keeps filters in paging / export links
        },
    )


@login_required
def event_detail(request, pk):
    event = get_object_or_404(Event.objects.select_related("camera", "acknowledged_by", "person"), pk=pk)
    return render(
        request,
        "events/event_detail.html",
        {
            "event": event,
            "people": Person.objects.filter(is_active=True),
            "history": event.assignments.select_related("changed_by", "from_person", "to_person")[:10],
        },
    )


def find_person(text: str):
    """Match what the operator typed: the full label, or just the employee code."""
    text = (text or "").strip()
    if not text:
        return None
    code = text.split("·", 1)[0].strip()
    return Person.objects.filter(employee_code__iexact=code, is_active=True).first()


@login_required
@require_POST
def event_assign_person(request, pk):
    """Operator answers "who is this?". Empty text clears the assignment."""
    event = get_object_or_404(Event, pk=pk)
    text = request.POST.get("person", "").strip()
    person = find_person(text)
    if text and person is None:
        messages.error(request, _("No active person matches “%(text)s”.") % {"text": text})
    else:
        if event.assign_person(person, request.user):
            messages.success(request, _("Person saved.") if person else _("Person removed."))
    return redirect("events:detail", pk=event.pk)


@login_required
@require_POST
def event_acknowledge(request, pk):
    event = get_object_or_404(Event, pk=pk)
    if event.is_open:
        event.acknowledge(request.user, note=request.POST.get("note", "").strip()[:1000])
        messages.success(request, _("Event acknowledged."))

    next_url = request.POST.get("next", "")
    if url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
        return redirect(next_url)
    return redirect("events:detail", pk=event.pk)


@login_required
def event_snapshot(request, pk):
    event = get_object_or_404(Event, pk=pk)
    if not event.snapshot or not event.snapshot.storage.exists(event.snapshot.name):
        raise Http404
    response = FileResponse(event.snapshot.open("rb"))
    response["Cache-Control"] = "private, max-age=3600"
    return response
