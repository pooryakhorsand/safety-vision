"""
Housekeeping used by the maintenance commands:

    purge_old_events()   delete events (and their files) older than the retention period
    backup_database()    write a dated copy of the database, keep the newest N copies

Kept as plain functions so the future launcher / service can call them too.
"""

import os
import shutil
import sqlite3
import subprocess
from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.db import connection
from django.utils import timezone

from apps.events.models import Event


def purge_old_events(retention_days: int | None = None) -> int:
    """Delete events that started before the retention window. Returns how many."""
    days = retention_days or settings.EVENT_RETENTION_DAYS
    cutoff = timezone.now() - timedelta(days=days)
    deleted = 0
    old_events = Event.objects.filter(started_at__lt=cutoff).only("pk", "snapshot", "clip")
    for event in old_events.iterator(chunk_size=500):
        event.delete()  # the post_delete signal removes the files
        deleted += 1
    _remove_empty_folders(Path(settings.MEDIA_ROOT) / "events")
    return deleted


def _remove_empty_folders(root: Path):
    if not root.exists():
        return
    for folder in sorted((p for p in root.rglob("*") if p.is_dir()), key=lambda p: len(p.parts), reverse=True):
        if not any(folder.iterdir()):
            folder.rmdir()


def backup_database(backup_dir: Path | None = None, keep: int | None = None) -> Path:
    """Back up the database to backup_dir and delete the oldest copies beyond `keep`."""
    target_dir = Path(backup_dir or settings.BACKUP_DIR)
    target_dir.mkdir(parents=True, exist_ok=True)
    stamp = timezone.localtime().strftime("%Y%m%d_%H%M%S")
    engine = settings.DATABASES["default"]["ENGINE"]

    if engine.endswith("sqlite3"):
        target = target_dir / f"db_{stamp}.sqlite3"
        connection.ensure_connection()
        destination = sqlite3.connect(target)
        try:
            connection.connection.backup(destination)  # safe while the app is running
        finally:
            destination.close()
        pattern = "db_*.sqlite3"
    elif engine.endswith("postgresql"):
        target = target_dir / f"db_{stamp}.dump"
        _pg_dump(target)
        pattern = "db_*.dump"
    else:
        raise RuntimeError(f"Backup is not supported for {engine}.")

    _keep_newest(target_dir, pattern, keep or settings.BACKUP_KEEP)
    return target


def _pg_dump(target: Path):
    executable = shutil.which("pg_dump")
    if not executable:
        raise RuntimeError("pg_dump was not found. Install the PostgreSQL client tools and add them to PATH.")
    db = settings.DATABASES["default"]
    env = {**os.environ, "PGPASSWORD": str(db.get("PASSWORD") or "")}
    subprocess.run(
        [
            executable,
            "--format=custom",
            "--file",
            str(target),
            "--host",
            str(db.get("HOST") or "127.0.0.1"),
            "--port",
            str(db.get("PORT") or 5432),
            "--username",
            str(db.get("USER") or ""),
            str(db["NAME"]),
        ],
        check=True,
        env=env,
    )


def _keep_newest(folder: Path, pattern: str, keep: int):
    backups = sorted(folder.glob(pattern), key=lambda p: p.name, reverse=True)
    for old in backups[max(1, keep) :]:
        old.unlink()
