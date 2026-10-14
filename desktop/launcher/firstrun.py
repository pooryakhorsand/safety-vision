"""First run: create the data folders, the secrets file and the engine settings. Never overwrites anything."""

from __future__ import annotations

import secrets
import shutil
from pathlib import Path

from desktop.launcher.layout import Layout

DATA_FOLDERS = ("config", "db", "media", "backups", "logs", "models", "queue", "cache")
ENV_TEMPLATE = """# Created on first run. Keep this file private: it holds the secrets of this installation.
DJANGO_DEBUG=False
DJANGO_SECRET_KEY={secret_key}
DJANGO_ALLOWED_HOSTS=127.0.0.1,localhost
ENGINE_API_TOKEN={engine_token}
SITE_PROFILE=default
"""


def ensure_data_folders(layout: Layout) -> None:
    for name in DATA_FOLDERS:
        (layout.data_dir / name).mkdir(parents=True, exist_ok=True)


def ensure_config(layout: Layout) -> list[str]:
    """Create config/.env and config/engine.yaml when missing. Returns what was created."""
    ensure_data_folders(layout)
    created = []

    env_file = layout.config_dir / ".env"
    if not env_file.exists():
        env_file.write_text(
            ENV_TEMPLATE.format(secret_key=secrets.token_urlsafe(50), engine_token=secrets.token_urlsafe(50)),
            encoding="utf-8",
        )
        created.append(".env")

    engine_file = layout.config_dir / "engine.yaml"
    if not engine_file.exists():
        shutil.copyfile(layout.app_dir / "desktop" / "config" / "engine.desktop.yaml", engine_file)
        created.append("engine.yaml")
    return created


def read_env_file(path: Path) -> dict[str, str]:
    """Plain KEY=VALUE lines (the launcher does not need python-dotenv)."""
    values = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip()
    return values
