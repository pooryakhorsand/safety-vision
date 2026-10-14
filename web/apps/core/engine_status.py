"""
Engine heartbeat: the engine posts its state every few seconds, the web app keeps
only the latest one (in the cache) and tells the browser whether the engine is alive.

Nothing here touches the database: a heartbeat is short-lived information.
"""

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

CACHE_KEY = "engine:heartbeat"
KEEP_SECONDS = 24 * 3600


def store_heartbeat(payload: dict) -> None:
    cache.set(CACHE_KEY, {"payload": payload, "received_at": timezone.now().timestamp()}, KEEP_SECONDS)


def _memory_percent(gpu):
    used, total = (gpu or {}).get("memory_used_mb"), (gpu or {}).get("memory_total_mb")
    return round(100 * used / total) if used is not None and total else None


def read_status() -> dict:
    """Everything the status bar, overview and live tiles need."""
    stored = cache.get(CACHE_KEY)
    offline = {
        "engine": {"state": "offline", "version": None, "uptime_seconds": None},
        "gpu": {"name": None, "memory_percent": None},
        "fps": None,
        "cameras": {"online": 0, "total": 0, "items": {}},
        "server_time": timezone.localtime().isoformat(),
    }
    if not stored:
        return offline

    age = timezone.now().timestamp() - stored["received_at"]
    if age > settings.ENGINE_HEARTBEAT_TIMEOUT_SECONDS:
        return offline

    payload = stored["payload"]
    cameras = payload.get("cameras") or []
    online = [c for c in cameras if c.get("online")]
    fps_values = [c["fps"] for c in online if c.get("fps") is not None]
    gpu = payload.get("gpu") or {}
    models_ok = payload.get("models_ok", True)
    return {
        "engine": {
            "state": "online" if models_ok else "error",  # "error": running, but model files are missing
            "version": payload.get("engine_version"),
            "uptime_seconds": payload.get("uptime_seconds"),
            "missing_models": payload.get("missing_models") or [],
        },
        "gpu": {"name": gpu.get("name"), "memory_percent": _memory_percent(gpu)},
        "fps": round(sum(fps_values) / len(fps_values), 1) if fps_values else None,
        "cameras": {
            "online": len(online),
            "total": len(cameras),
            "items": {
                str(c["id"]): {"online": bool(c.get("online")), "fps": c.get("fps"), "mode": c.get("mode", "live")}
                for c in cameras
                if "id" in c
            },
        },
        "server_time": timezone.localtime().isoformat(),
    }
