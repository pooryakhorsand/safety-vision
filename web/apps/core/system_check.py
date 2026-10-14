"""
What the desktop launcher found about this computer (GPU, CUDA, disk space, model files).

The launcher writes <data folder>/config/system_check.json when the app starts; Django only reads it.
Without that file (a development setup) the panel says the check is only available in the installed app.
"""

import json
from datetime import datetime

from django.conf import settings

from apps.core.engine_status import read_status
from apps.core.profile_loader import get_profile


def read_system_check() -> dict:
    path = settings.DATA_DIR / "config" / "system_check.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = None

    status = read_status()
    models = (data or {}).get("models", [])
    return {
        "available": data is not None,
        "checked_at": _parse_time((data or {}).get("checked_at")),
        "gpu": (data or {}).get("gpu"),
        "cuda_available": (data or {}).get("cuda_available"),
        "disk": (data or {}).get("disk"),
        "models": models,
        "missing_models": [m for m in models if not m.get("found")],
        "engine_failed": bool((data or {}).get("engine_failed")),
        "engine_state": status["engine"]["state"],
        "models_dir": str(settings.DATA_DIR / "models"),
        "releases_url": get_profile().releases_url,
    }


def _parse_time(value):
    try:
        return datetime.fromisoformat(value) if value else None
    except ValueError:
        return None
