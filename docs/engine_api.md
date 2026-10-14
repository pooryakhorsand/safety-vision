# Engine ↔ Web API

The engine (GPU process, own environment) and the web app (Django) talk over
HTTP on the local machine. The web app owns the database; the engine never
connects to it.

Every engine call carries the shared token from `.env`:

```
Authorization: Bearer <ENGINE_API_TOKEN>
```

Missing or wrong token → `401`. Token not configured on the server → `503`.

## 1. Read the camera list

`GET /api/engine/cameras/`

```json
{
  "cameras": [
    {"id": 1, "name": "CAM-01", "source_url": "rtsp://127.0.0.1:8554/cam1", "modules": ["ppe"]},
    {"id": 2, "name": "CAM-02", "source_url": "rtsp://127.0.0.1:8554/cam2", "modules": ["ppe"]}
  ]
}
```

Only enabled cameras are listed. `modules` = the modules the engine must run on that camera.

## 2. Report an event

`POST /api/events/` — `multipart/form-data` (to include a snapshot) or `application/json`.

One violation = one event with one `uid` chosen by the engine:

| When | Send |
|------|------|
| Violation becomes stable (e.g. 3 s) | `uid`, `camera_id`, `module`, `event_type`, `started_at`, `track_id`, `confidence`, `snapshot` |
| Violation ends | `uid`, `ended_at` |
| The same person violates again within the merge window | `uid` (the SAME one), `ended_at` = empty / `null`, `occurrences`, `last_seen_at` |

The same `uid` always updates the same row, so retries are safe.

**Reopen:** an `ended_at` that is present but empty (`""` in form-data, `null` in JSON) on an
existing event clears the end time. If an operator had already acknowledged the event, it goes
back to *open*, because there is a new violation to look at. Leaving `ended_at` out changes nothing.

**Who is this?** The engine never sends a name or an employee. Only an operator assigns a person
in the web app; a `person` field in the request is ignored.

| Field | Required | Notes |
|-------|----------|-------|
| `uid` | always | UUID |
| `camera_id` | on create | `id` from the camera list |
| `module` | on create | `ppe` |
| `event_type` | on create | must belong to the module (see below) |
| `started_at` | on create | ISO 8601 with time zone |
| `ended_at` | no | ISO 8601, not before `started_at` |
| `occurrences` | no | integer ≥ 1: how many separate times it happened (merged repeats) |
| `last_seen_at` | no | ISO 8601, last time the violation was seen |
| `track_id` | no | tracker ID of the person |
| `confidence` | no | 0..1 |
| `severity` | no | `info` / `warning` / `critical`; default comes from the event type |
| `extra` | no | JSON object (bbox, zone, …), merged on update; `extra.track_ids` lists are united, not replaced |
| `snapshot` | no | JPEG / PNG / WebP, max 10 MB, multipart only |

Event types:

| Module | `event_type` | Default severity |
|--------|--------------|------------------|
| `ppe` | `no_helmet` | critical |
| `ppe` | `no_vest` | warning |
| `ppe` | `no_safety_shoes` | warning |

Responses: `201` created, `200` updated, `400` with `{"error": ..., "fields": ...}`.

### Example (Python, `requests`)

```python
import uuid, datetime, requests

API = "http://127.0.0.1:8000/api"
HEADERS = {"Authorization": "Bearer <ENGINE_API_TOKEN>"}
uid = str(uuid.uuid4())

# start
with open("frame.jpg", "rb") as image:
    requests.post(
        f"{API}/events/",
        headers=HEADERS,
        files={"snapshot": image},
        data={
            "uid": uid,
            "camera_id": 1,
            "module": "ppe",
            "event_type": "no_helmet",
            "started_at": datetime.datetime.now().astimezone().isoformat(),
            "track_id": 3,
            "confidence": 0.91,
        },
    ).raise_for_status()

# end
requests.post(
    f"{API}/events/",
    headers=HEADERS,
    json={
        "uid": uid,
        "ended_at": datetime.datetime.now().astimezone().isoformat(),
    },
).raise_for_status()
```

## 3. Heartbeat

`POST /api/engine/heartbeat/` — JSON, every few seconds (`web.heartbeat_seconds`).

```json
{
  "engine_version": "0.1.0",
  "uptime_seconds": 3600,
  "gpu": {"name": "GTX 1650", "memory_used_mb": 1800, "memory_total_mb": 4096},
  "cameras": [
    {"id": 1, "online": true, "fps": 14.8, "latency_ms": 62.0, "mode": "live", "open_events": 1}
  ]
}
```

The web app keeps only the latest heartbeat (cache, not the database). No heartbeat for
`ENGINE_HEARTBEAT_TIMEOUT_SECONDS` (default 20) means the engine is shown as offline.
`mode` is `live` for real cameras and `replay` when the engine plays back a recording; the UI
shows a "Recorded" badge for `replay`. `GET /api/system/status/` (signed-in users) returns the
combined state for the status bar and the live tiles.

## 4. Live view

The engine serves MJPEG on its own port (`render.stream_port`): `GET <ENGINE_STREAM_URL>/stream/<camera_id>`.
The live tile points an `<img>` at it while the camera is online. Django never touches video.

The source of truth for modules and event types is
`web/apps/vision_modules/registry.py`; update this table when it changes.
