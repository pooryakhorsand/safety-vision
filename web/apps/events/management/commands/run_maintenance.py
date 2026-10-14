"""
Daily housekeeping. Schedule it once a day (Windows Task Scheduler / cron):

    python manage.py run_maintenance                 # purge old events + back up the database
    python manage.py run_maintenance --skip-backup   # purge only
    python manage.py run_maintenance --skip-purge    # backup only

Retention days come from profile.yaml; backup folder and count from .env.
"""

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.events.maintenance import backup_database, purge_old_events


class Command(BaseCommand):
    help = "Delete events older than the retention period and back up the database."

    def add_arguments(self, parser):
        parser.add_argument("--skip-purge", action="store_true")
        parser.add_argument("--skip-backup", action="store_true")

    def handle(self, *args, **options):
        if not options["skip_purge"]:
            deleted = purge_old_events()
            self.stdout.write(f"Purge: {deleted} event(s) older than {settings.EVENT_RETENTION_DAYS} day(s) deleted.")

        if not options["skip_backup"]:
            try:
                path = backup_database()
            except Exception as error:  # report clearly, keep the exit code non-zero
                raise CommandError(f"Backup failed: {error}") from error
            self.stdout.write(f"Backup: {path}")

        self.stdout.write(self.style.SUCCESS("Maintenance finished."))
