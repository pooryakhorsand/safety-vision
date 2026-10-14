"""
Live mode: keeps the cameras from the web app running, sends events and a heartbeat.

Cameras are re-read from the web app every `web.cameras_refresh_seconds`, so a camera added or
edited in Settings starts (or restarts) without restarting the engine.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable

from engine import __version__
from engine.core.config import EngineConfig
from engine.core.pipeline import Pipeline
from engine.core.sources import FrameSource, now_utc, open_source

log = logging.getLogger(__name__)
RETRY_FIRST_SYNC_SECONDS = 5.0


def gpu_status(config: EngineConfig) -> dict | None:
    """GPU name and memory for the heartbeat. None on CPU or when torch is missing."""
    if str(config.device.gpu).lower() == "cpu":
        return None
    try:
        import torch

        if not torch.cuda.is_available():
            return None
        index = int(config.device.gpu)
        free, total = torch.cuda.mem_get_info(index)
        return {
            "name": torch.cuda.get_device_name(index),
            "memory_used_mb": round((total - free) / 1024**2),
            "memory_total_mb": round(total / 1024**2),
        }
    except Exception:
        return None


class LiveRunner:
    def __init__(
        self,
        config: EngineConfig,
        client,
        pipeline: Pipeline,
        *,
        source_factory: Callable[..., FrameSource] = open_source,
        on_frame: Callable | None = None,
        mode: str = "live",
    ):
        self.config = config
        self.client = client
        self.pipeline = pipeline
        self.source_factory = source_factory
        self.on_frame = on_frame  # called with (runtime, frame_result) after each frame
        self.mode = mode
        self.started = time.monotonic()

    # ------------------------------------------------------------ cameras
    def sync_cameras(self, cameras: list[dict]) -> None:
        wanted = {int(c["id"]): c for c in cameras}
        for camera_id in [i for i in self.pipeline.runtimes if i not in wanted]:
            log.info("camera %s removed", camera_id)
            self.pipeline.remove_camera(camera_id, now_utc())
        for camera_id, camera in wanted.items():
            current = self.pipeline.runtimes.get(camera_id)
            if current is not None and _same_camera(current.camera, camera):
                continue
            if current is not None:
                log.info("camera %s changed, restarting it", camera_id)
                self.pipeline.remove_camera(camera_id, now_utc())
            source = self.source_factory(
                camera.get("name", f"CAM-{camera_id}"),
                camera["source_url"],
                loop=self.config.sources.loop_files,
                reconnect_seconds=self.config.sources.reconnect_seconds,
            )
            source.start()
            self.pipeline.add_camera(camera, source, mode=self.mode)
            log.info("camera %s started (%s)", camera_id, camera.get("name"))

    # ------------------------------------------------------------ heartbeat
    def heartbeat_payload(self) -> dict:
        status = self.pipeline.status()
        status.update(
            {
                "engine_version": __version__,
                "models_ok": True,
                "uptime_seconds": round(time.monotonic() - self.started),
                "gpu": gpu_status(self.config),
            }
        )
        return status

    # ------------------------------------------------------------ main loop
    def run(self, stop: threading.Event) -> None:
        web = self.config.web
        next_sync = next_heartbeat = 0.0
        try:
            while not stop.is_set():
                now = time.monotonic()
                if now >= next_sync:
                    try:
                        self.sync_cameras(self.client.get_cameras())
                        next_sync = now + web.cameras_refresh_seconds
                    except Exception as error:  # web app down: keep what runs, try again soon
                        log.warning("cannot read the camera list (%s); retrying", error.__class__.__name__)
                        next_sync = now + min(RETRY_FIRST_SYNC_SECONDS, web.cameras_refresh_seconds)
                if now >= next_heartbeat:
                    self.client.send_heartbeat(self.heartbeat_payload())
                    next_heartbeat = now + web.heartbeat_seconds

                worked = False
                for runtime in list(self.pipeline.runtimes.values()):
                    ok, frame, timestamp = runtime.source.read(timeout=0)
                    if not ok:
                        continue
                    worked = True
                    result = self.pipeline.process_frame(runtime, frame, timestamp)
                    if self.on_frame:
                        self.on_frame(runtime, result)
                if not worked:
                    stop.wait(0.005)
        finally:
            self.pipeline.close_all(now_utc())
            self.client.flush(5.0)


def _same_camera(a: dict, b: dict) -> bool:
    return a.get("source_url") == b.get("source_url") and sorted(a.get("modules") or []) == sorted(
        b.get("modules") or []
    )
