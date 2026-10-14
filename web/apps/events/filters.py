"""
Filter form for the management channel.

The same form drives the table, the CSV export and the printable report,
so all three always show exactly the same events.
"""

from datetime import datetime, time

from django import forms
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.cameras.models import Camera
from apps.events.models import Event
from apps.people.models import Person
from apps.vision_modules.registry import get_enabled_modules


class EventFilterForm(forms.Form):
    date_from = forms.DateField(label=_("From"), required=False, widget=forms.DateInput(attrs={"type": "date"}))
    date_to = forms.DateField(label=_("To"), required=False, widget=forms.DateInput(attrs={"type": "date"}))
    module = forms.ChoiceField(label=_("Module"), required=False)
    event_type = forms.ChoiceField(label=_("Event type"), required=False)
    camera = forms.ChoiceField(label=_("Camera"), required=False)
    status = forms.ChoiceField(label=_("Status"), required=False)
    person = forms.ChoiceField(label=_("Person"), required=False)
    track_id = forms.IntegerField(label=_("Track ID"), required=False, min_value=0)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        modules = get_enabled_modules()
        everything = [("", _("All"))]
        self.fields["module"].choices = everything + [(m.key, m.name) for m in modules]
        self.fields["event_type"].choices = everything + [
            (t.key, f"{m.name} · {t.name}") for m in modules for t in m.event_types
        ]
        self.fields["camera"].choices = everything + [(str(c.pk), c.name) for c in Camera.objects.all()]
        self.fields["person"].choices = (
            everything + [("none", _("Not assigned"))] + [(str(p.pk), p.label) for p in Person.objects.all()]
        )
        self.fields["status"].choices = everything + list(Event.Status.choices)

    def clean(self):
        data = super().clean()
        if data.get("date_from") and data.get("date_to") and data["date_to"] < data["date_from"]:
            self.add_error("date_to", _("End date is before start date."))
        return data

    @property
    def is_filtered(self) -> bool:
        return self.is_bound and self.is_valid() and any(v not in (None, "") for v in self.cleaned_data.values())

    def apply(self, queryset):
        """Return the queryset narrowed by the valid filters (invalid ones are ignored)."""
        if not self.is_bound or not self.is_valid():
            return queryset
        data = self.cleaned_data
        zone = timezone.get_current_timezone()
        if data.get("date_from"):
            queryset = queryset.filter(started_at__gte=datetime.combine(data["date_from"], time.min, tzinfo=zone))
        if data.get("date_to"):
            queryset = queryset.filter(started_at__lte=datetime.combine(data["date_to"], time.max, tzinfo=zone))
        if data.get("module"):
            queryset = queryset.filter(module_key=data["module"])
        if data.get("event_type"):
            queryset = queryset.filter(event_type=data["event_type"])
        if data.get("camera"):
            queryset = queryset.filter(camera_id=int(data["camera"]))
        if data.get("status"):
            queryset = queryset.filter(status=data["status"])
        if data.get("person") == "none":
            queryset = queryset.filter(person__isnull=True)
        elif data.get("person"):
            queryset = queryset.filter(person_id=int(data["person"]))
        if data.get("track_id") is not None:
            queryset = queryset.filter(track_id=data["track_id"])
        return queryset
