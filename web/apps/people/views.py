"""
People pages.

    person_list           search + table                       (all signed-in users)
    person_detail         one person: violations, last 30 days (all signed-in users)
    person_create / edit  admin only
    person_toggle_active  admin only (a person who left stays in old events)
"""

from datetime import timedelta

from django.contrib import messages
from django.db.models import Count, Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from apps.core.permissions import admin_required, login_required
from apps.events.models import Event
from apps.people.forms import PersonForm
from apps.people.models import Person
from apps.vision_modules.registry import get_any_module

HISTORY_DAYS = 30
RECENT_EVENTS = 15


@login_required
def person_list(request):
    query = request.GET.get("q", "").strip()
    people = Person.objects.all()
    if query:
        people = people.filter(
            Q(employee_code__icontains=query) | Q(full_name__icontains=query) | Q(department__icontains=query)
        )
    if request.GET.get("show") != "all":
        people = people.filter(is_active=True)
    return render(
        request,
        "people/person_list.html",
        {
            "people": people,
            "query": query,
            "show_all": request.GET.get("show") == "all",
        },
    )


def _type_name(module_key: str, event_type: str) -> str:
    module = get_any_module(module_key)
    kind = module.get_event_type(event_type) if module else None
    return str(kind.name) if kind else event_type


@login_required
def person_detail(request, pk):
    person = get_object_or_404(Person, pk=pk)
    since = timezone.now() - timedelta(days=HISTORY_DAYS)
    events = Event.objects.filter(person=person)
    recent = events.filter(started_at__gte=since)

    rows = (
        recent.values("module_key", "event_type")
        .annotate(events=Count("id"), times=Sum("occurrences"))
        .order_by("-events")
    )
    by_type = [
        {
            "name": _type_name(row["module_key"], row["event_type"]),
            "events": row["events"],
            "times": row["times"] or row["events"],
        }
        for row in rows
    ]
    return render(
        request,
        "people/person_detail.html",
        {
            "person": person,
            "days": HISTORY_DAYS,
            "by_type": by_type,
            "total_events": recent.count(),
            "recent_events": events.select_related("camera")[:RECENT_EVENTS],
        },
    )


@admin_required
def person_create(request):
    form = PersonForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        person = form.save()
        messages.success(request, _("“%(name)s” was added.") % {"name": person.full_name})
        return redirect("people:detail", pk=person.pk)
    return render(request, "people/person_form.html", {"form": form, "person": None})


@admin_required
def person_edit(request, pk):
    person = get_object_or_404(Person, pk=pk)
    form = PersonForm(request.POST or None, instance=person)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, _("Changes saved."))
        return redirect("people:detail", pk=person.pk)
    return render(request, "people/person_form.html", {"form": form, "person": person})


@admin_required
@require_POST
def person_toggle_active(request, pk):
    person = get_object_or_404(Person, pk=pk)
    person.is_active = not person.is_active
    person.save(update_fields=["is_active", "updated_at"])
    messages.success(request, _("Status updated."))
    return redirect("people:detail", pk=person.pk)
