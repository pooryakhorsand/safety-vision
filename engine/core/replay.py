"""
Replay mode: plays the results of offline mode like a live camera.

For one camera it plays rendered.mp4 in real time (to the live view) and, at the right moments,
sends the recorded events through the SAME web API a live camera uses (new uids on every pass,
times shifted to "now"). The web app cannot tell the difference, and the heartbeat marks the
camera as mode "replay" so the interface can show a "Recorded" badge.
"""

from __future__ import annotations

import json
import logging
import threading
import time
import uuid
from collections.abc import Callable
from datetime import timedelta
from pathlib import Path

import cv2

from engine.core.sources import now_utc

log = logging.getLogger(__name__)


def load_events(directory: Path) -> list[dict]:
    path = Path(directory) / "events.jsonl"
    lines = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    return sorted(lines, key=lambda line: line["send_t"])


class ReplayCamera:
    """One recorded camera. run() loops until `stop` is set."""

    def __init__(
        self,
        camera_id: int,
        directory: Path,
        client,
        *,
        loop: bool = True,
        on_frame: Callable | None = None,
        speed: float = 1.0,
    ):
        self.camera_id = camera_id
        self.directory = Path(directory)
        self.client = client
        self.loop = loop
        self.on_frame = on_frame  # called with (camera_id, bgr_image)
        self.speed = speed  # 1.0 = real time; tests use a large number
        self.events = load_events(self.directory)
        self.fps = 25.0
        self.passes = 0

    def status(self) -> dict:
        return {
            "id": self.camera_id,
            "online": True,
            "fps": round(self.fps, 1),
            "latency_ms": 0.0,
            "mode": "replay",
            "open_events": 0,
        }

    def run(self, stop: threading.Event) -> None:
        while not stop.is_set():
            self._play_once(stop)
            self.passes += 1
            if not self.loop:
                return

    def _play_once(self, stop: threading.Event) -> None:
        capture = cv2.VideoCapture(str(self.directory / "rendered.mp4"))
        if not capture.isOpened():
            raise FileNotFoundError(f"cannot open {self.directory / 'rendered.mp4'}")
        self.fps = capture.get(cv2.CAP_PROP_FPS) or 25.0
        base = now_utc()  # video second 0 = now
        uids: dict[str, str] = {}  # recorded uid -> uid of this pass
        next_event = 0
        wall_start = time.monotonic()
        index = 0
        try:
            while not stop.is_set():
                ok, frame = capture.read()
                if not ok:
                    break
                video_time = index / self.fps
                while next_event < len(self.events) and self.events[next_event]["send_t"] <= video_time:
                    self._send(self.events[next_event], base, uids)
                    next_event += 1
                if self.on_frame:
                    self.on_frame(self.camera_id, frame)
                index += 1
                delay = wall_start + video_time / self.speed - time.monotonic() + 1 / self.fps / self.speed
                if delay > 0:
                    stop.wait(delay)
            while next_event < len(self.events):  # events after the last frame (final "end" lines)
                self._send(self.events[next_event], base, uids)
                next_event += 1
        finally:
            capture.release()

    def _send(self, line: dict, base, uids: dict[str, str]) -> None:
        payload = dict(line["payload"])
        recorded_uid = payload["uid"]
        payload["uid"] = uids.setdefault(recorded_uid, str(uuid.uuid4()))
        when = (base + timedelta(seconds=line["t"])).isoformat()
        if line["kind"] == "create":
            payload["started_at"] = when
            payload["camera_id"] = self.camera_id
        elif line["kind"] == "reopen":
            payload["last_seen_at"] = when
        else:
            payload["ended_at"] = payload["last_seen_at"] = when
        snapshot = None
        if line.get("snapshot"):
            snapshot_file = self.directory / line["snapshot"]
            if snapshot_file.exists():
                snapshot = snapshot_file.read_bytes()
        self.client.send_event(payload, snapshot)
