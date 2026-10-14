"""
Offline mode: process a video file as fast as the machine allows (no real-time pace).

Writes into the output folder:
    rendered.mp4     the picture with boxes and tags (H.264)
    events.jsonl     one line per event action, with its VIDEO time (so replay can re-send it later)
    snapshots/       evidence images of new events

Needs no web app. Replay mode (core/replay.py) plays these files back like a camera.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from engine.core.config import EngineConfig
from engine.core.pipeline import Pipeline
from engine.core.sources import iter_video, now_utc
from engine.render.overlay import FrameRenderer
from engine.render.video_writer import VideoWriter

log = logging.getLogger(__name__)

EVENT_TIME_FIELDS = ("started_at", "ended_at", "last_seen_at")


class JsonlSink:
    """Event sink that writes lines to a file instead of calling the web app."""

    def __init__(self, out_dir: Path, start_time: datetime):
        self.out_dir = Path(out_dir)
        (self.out_dir / "snapshots").mkdir(parents=True, exist_ok=True)
        self.start_time = start_time
        self._file = open(self.out_dir / "events.jsonl", "w", encoding="utf-8")
        self.count = 0

    def send_event(self, payload: dict, snapshot: bytes | None = None, *, at: datetime | None = None) -> None:
        kind = "create" if "event_type" in payload else ("end" if payload.get("ended_at") else "reopen")
        field = {"create": "started_at", "end": "ended_at", "reopen": "last_seen_at"}[kind]
        event_time = datetime.fromisoformat(payload[field])
        line = {
            "send_t": round(((at or event_time) - self.start_time).total_seconds(), 3),  # when the engine emitted it
            "t": round((event_time - self.start_time).total_seconds(), 3),  # when it happened
            "kind": kind,
            "payload": payload,
            "snapshot": None,
        }
        if snapshot:
            name = f"snapshots/{payload['uid']}.jpg"
            (self.out_dir / name).write_bytes(snapshot)
            line["snapshot"] = name
        self._file.write(json.dumps(line) + "\n")
        self._file.flush()
        self.count += 1

    def close(self) -> None:
        self._file.close()


@dataclass
class OfflineSummary:
    frames: int
    events: int
    seconds: float


def run_offline(
    config: EngineConfig,
    pipeline_factory,
    video: Path,
    out_dir: Path,
    *,
    camera: dict,
    start_time: datetime | None = None,
) -> OfflineSummary:
    """
    pipeline_factory(sink) -> Pipeline   builds the pipeline with the given event sink
    (real runs pass real detectors; tests pass scripted detectors from engine/tests/fakes.py).
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    start_time = start_time or now_utc()
    sink = JsonlSink(out_dir, start_time)
    pipeline: Pipeline = pipeline_factory(sink)
    runtime = pipeline.add_camera(camera, None, mode="offline")
    renderer = FrameRenderer(config)

    writer = None
    frames = 0
    last_time = start_time
    try:
        for index, frame, timestamp, fps in iter_video(video, start_time):
            result = pipeline.process_frame(runtime, frame, timestamp)
            picture = renderer.render(result.ctx)
            if writer is None:
                height, width = picture.shape[:2]
                writer = VideoWriter(out_dir / "rendered.mp4", fps, (width, height), config.render.crf)
            writer.write(picture)
            frames, last_time = index + 1, timestamp
            if frames % 100 == 0:
                log.info("offline: %d frames, %d events so far", frames, sink.count)
        pipeline.close_all(last_time)  # events still open at the end of the video are closed
    finally:
        if writer is not None:
            writer.close()
        sink.close()
    return OfflineSummary(frames, sink.count, (last_time - start_time).total_seconds())
