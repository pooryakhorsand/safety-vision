"""Shared test helpers. Everything here runs without a GPU, model weights or the web app."""

from __future__ import annotations

import copy
import json
import threading
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import cv2
import numpy as np
import pytest

from engine.core.config import EngineConfig, parse_config
from engine.core.frame import Detection

BASE = {
    "detectors": {"person": {"weights": "person.pt"}, "equipment": {"weights": "equipment.pt"}},
    "tracker": {"type": "iou"},
    "reid": {"backend": "histogram", "sample_every_frames": 1, "crops_per_track": 3, "merge_threshold": 0.75},
    "events": {"confirm_seconds": 1.0, "clear_seconds": 1.0, "pending_grace_seconds": 0.3, "merge_window_minutes": 10},
    "modules": {"ppe": {"vote_window": 5, "min_votes": 2}},
}

T0 = datetime(2026, 1, 1, 10, 0, 0, tzinfo=UTC)


def make_config(**overrides) -> EngineConfig:
    """Config for tests; `overrides` are merged into BASE section by section."""
    data = copy.deepcopy(BASE)
    for section, values in overrides.items():
        if isinstance(values, dict) and isinstance(data.get(section), dict):
            data[section].update(values)
        else:
            data[section] = values
    return parse_config(data, env={"ENGINE_API_TOKEN": "test-token"})


def at(seconds: float) -> datetime:
    return T0 + timedelta(seconds=seconds)


def det(name: str, box, conf: float = 0.9) -> Detection:
    return Detection(name, conf, tuple(float(v) for v in box))


def scene(people=(), size=(480, 640)) -> np.ndarray:
    """Black picture with one coloured rectangle per person: people = [(box, (b, g, r)), ...]."""
    image = np.zeros((*size, 3), np.uint8)
    for (x1, y1, x2, y2), color in people:
        image[int(y1) : int(y2), int(x1) : int(x2)] = color
    return image


def write_video(path, frames: int = 10, fps: int = 10, size=(64, 48)) -> None:
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"MJPG"), fps, size)
    for i in range(frames):
        writer.write(np.full((size[1], size[0], 3), i * 10, np.uint8))
    writer.release()


class CollectingSink:
    """Event sink that just remembers what it was given."""

    def __init__(self):
        self.calls: list[tuple[dict, bytes | None]] = []

    def send_event(self, payload, snapshot=None, *, at=None):
        self.calls.append((payload, snapshot))

    @property
    def payloads(self):
        return [payload for payload, _ in self.calls]


class FakeWeb:
    """A tiny local HTTP server that plays the role of the Django app."""

    def __init__(self):
        self.requests: list[dict] = []
        self.status = 200
        self.cameras = [{"id": 1, "name": "CAM-01", "source_url": "0", "modules": ["ppe"]}]
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def _answer(self, body: dict, status: int):
                data = json.dumps(body).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self):  # noqa: N802
                outer.requests.append({"method": "GET", "path": self.path, "auth": self.headers.get("Authorization")})
                self._answer({"cameras": outer.cameras}, outer.status)

            def do_POST(self):  # noqa: N802
                length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(length)
                outer.requests.append(
                    {
                        "method": "POST",
                        "path": self.path,
                        "auth": self.headers.get("Authorization"),
                        "type": self.headers.get("Content-Type", ""),
                        "body": body,
                    }
                )
                self._answer({"ok": True}, outer.status)

            def log_message(self, *args):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.server.server_address[1]}"

    def json_posts(self):
        return [json.loads(r["body"]) for r in self.requests if r["method"] == "POST" and "json" in r["type"]]

    def close(self):
        self.server.shutdown()
        self.server.server_close()


@pytest.fixture
def web():
    server = FakeWeb()
    yield server
    server.close()
