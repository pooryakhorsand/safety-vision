"""CSV export of the filtered events (opens correctly in Excel, including Persian text)."""

import csv

from django.http import HttpResponse
from django.utils import timezone
from django.utils.translation import gettext as _


def _local(value):
    return timezone.localtime(value).strftime("%Y-%m-%d %H:%M:%S") if value else ""


def events_to_csv(events) -> HttpResponse:
    filename = f"events_{timezone.localtime():%Y%m%d_%H%M}.csv"
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    response.write("﻿")  # byte-order mark: tells Excel the file is UTF-8

    writer = csv.writer(response)
    writer.writerow(
        [
            _("ID"),
            _("Started at"),
            _("Ended at"),
            _("Duration (s)"),
            _("Camera"),
            _("Module"),
            _("Event type"),
            _("Severity"),
            _("Person"),
            _("Occurrences"),
            _("Track ID"),
            _("Confidence"),
            _("Status"),
            _("Acknowledged by"),
            _("Acknowledged at"),
            _("Note"),
        ]
    )
    for event in events.select_related("acknowledged_by", "person").iterator():
        writer.writerow(
            [
                event.pk,
                _local(event.started_at),
                _local(event.ended_at),
                int(event.duration.total_seconds()) if event.ended_at else "",
                event.camera_name,
                event.module_name,
                event.type_name,
                event.get_severity_display(),
                event.person.label if event.person else "",
                event.occurrences,
                event.track_id if event.track_id is not None else "",
                f"{event.confidence:.2f}" if event.confidence is not None else "",
                event.get_status_display(),
                event.acknowledged_by.display_name if event.acknowledged_by else "",
                _local(event.acknowledged_at),
                event.note,
            ]
        )
    return response
