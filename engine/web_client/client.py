"""
The ONLY code that talks to the web app (Django).

  get_cameras()        the camera list (needs the web app to be up)
  send_event(...)      queued: written to disk first, a background thread delivers it
  send_heartbeat(...)  best effort, never queued

Why a queue? The video pipeline must never wait for the network, and an event must
never be lost because the web app was restarting. Events are delivered oldest first
(a "create" must reach the server before its "end"), and retrying is safe because the
server treats the same uid as the same event.

Queue files in queue_dir:   <number>.json (+ <number>.jpg snapshot)
Rejected by the server (HTTP 4xx other than 401/403/408/429) go to queue_dir/rejected/.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from pathlib import Path

import requests

from engine.core.config import WebConfig, resolve_path

log = logging.getLogger(__name__)

RETRY_STATUS = {401, 403, 408, 429}  # config / load problems: keep the event and try again later


class WebClient:
    def __init__(self, config: WebConfig, retry_seconds: float = 2.0, max_retry_seconds: float = 30.0):
        self.base_url = config.base_url.rstrip("/")
        self.timeout = config.timeout_seconds
        self.retry_seconds = retry_seconds
        self.max_retry_seconds = max_retry_seconds
        self.queue_dir = resolve_path(config.queue_dir)
        self.queue_dir.mkdir(parents=True, exist_ok=True)
        (self.queue_dir / "rejected").mkdir(exist_ok=True)

        self._session = requests.Session()
        if config.token:
            self._session.headers["Authorization"] = f"Bearer {config.token}"
        else:
            log.warning(
                "no engine API token (environment variable %s is empty): the web app will refuse requests",
                config.token_env,
            )

        self._lock = threading.Lock()
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._counter = 0
        self._worker: threading.Thread | None = None

    # ------------------------------------------------------------ cameras
    def get_cameras(self) -> list[dict]:
        """Raises requests.RequestException when the web app cannot be reached."""
        response = self._session.get(f"{self.base_url}/api/engine/cameras/", timeout=self.timeout)
        response.raise_for_status()
        return response.json().get("cameras", [])

    # ------------------------------------------------------------ heartbeat
    def send_heartbeat(self, status: dict) -> bool:
        try:
            response = self._session.post(f"{self.base_url}/api/engine/heartbeat/", json=status, timeout=self.timeout)
            return response.ok
        except requests.RequestException:
            return False

    # ------------------------------------------------------------ events
    def send_event(self, payload: dict, snapshot: bytes | None = None, *, at=None) -> None:
        """Put an event call in the queue and return at once. (`at` is only used by the offline file sink.)"""
        with self._lock:
            self._counter += 1
            number = f"{time.time_ns()}{self._counter % 1000:03d}"
            if snapshot:
                (self.queue_dir / f"{number}.jpg").write_bytes(snapshot)
            tmp = self.queue_dir / f"{number}.tmp"
            tmp.write_text(json.dumps({"payload": payload, "snapshot": bool(snapshot)}), encoding="utf-8")
            tmp.rename(self.queue_dir / f"{number}.json")  # appears fully written or not at all
        self._wake.set()

    def pending(self) -> int:
        return len(list(self.queue_dir.glob("*.json")))

    def start(self) -> "WebClient":
        if self._worker is None:
            self._worker = threading.Thread(target=self._deliver_loop, name="web-queue", daemon=True)
            self._worker.start()
        return self

    def flush(self, timeout: float = 10.0) -> bool:
        """Wait until the queue is empty. Returns False on timeout."""
        deadline = time.monotonic() + timeout
        while self.pending() and time.monotonic() < deadline:
            self._wake.set()
            time.sleep(0.05)
        return self.pending() == 0

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()
        if self._worker is not None:
            self._worker.join(timeout=5)
            self._worker = None

    # ------------------------------------------------------------ worker
    def _deliver_loop(self) -> None:
        delay = self.retry_seconds
        while not self._stop.is_set():
            files = sorted(self.queue_dir.glob("*.json"))
            if not files:
                self._wake.wait(timeout=1.0)
                self._wake.clear()
                continue
            outcome = self._deliver(files[0])
            if outcome == "retry":
                self._stop.wait(delay)
                delay = min(delay * 2, self.max_retry_seconds)
            else:
                delay = self.retry_seconds

    def _deliver(self, json_file: Path) -> str:
        """Returns 'done', 'rejected' or 'retry'."""
        try:
            item = json.loads(json_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            self._reject(json_file)
            return "rejected"
        snapshot_file = json_file.with_suffix(".jpg")
        try:
            if item.get("snapshot") and snapshot_file.exists():
                data = {k: _form_value(v) for k, v in item["payload"].items()}
                response = self._session.post(
                    f"{self.base_url}/api/events/",
                    data=data,
                    timeout=self.timeout,
                    files={"snapshot": (snapshot_file.name, snapshot_file.read_bytes(), "image/jpeg")},
                )
            else:
                response = self._session.post(
                    f"{self.base_url}/api/events/", json=item["payload"], timeout=self.timeout
                )
        except requests.RequestException as error:
            log.warning(
                "web app not reachable (%s); %d event call(s) waiting", error.__class__.__name__, self.pending()
            )
            return "retry"

        if response.ok:
            json_file.unlink(missing_ok=True)
            snapshot_file.unlink(missing_ok=True)
            return "done"
        if response.status_code >= 500 or response.status_code in RETRY_STATUS:
            log.warning("web app answered %s; will retry", response.status_code)
            return "retry"
        log.error("web app rejected an event call (%s): %s", response.status_code, response.text[:300])
        self._reject(json_file)
        return "rejected"

    def _reject(self, json_file: Path) -> None:
        target = self.queue_dir / "rejected"
        for file in (json_file, json_file.with_suffix(".jpg")):
            if file.exists():
                file.replace(target / file.name)


def _form_value(value):
    """multipart form fields are text: lists/dicts become JSON, None becomes an empty field."""
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value)
    return value
