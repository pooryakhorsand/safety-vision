"""
The per-camera processing chain.

    frame -> person detector -> tracker -> extra detectors (what the modules need)
          -> modules -> observations -> event state machine -> actions
          -> snapshot + gallery update -> event sink (web queue, or a file when offline)

This file wires the parts together; it holds no detection or business rules itself.
Drawing is NOT done here: callers (live view, offline writer) call render_frame() on the result.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol

from engine.core.config import EngineConfig
from engine.core.frame import FrameContext, Observation
from engine.core.sources import FrameSource
from engine.events.snapshot import make_snapshot
from engine.events.state_machine import EventAction, MergeTarget, StateMachine, to_payload
from engine.identity.recent_gallery import RecentGallery
from engine.modules.base import MODULE_REGISTRY, VisionModule, create_modules
from engine.perception.detector import Detector
from engine.perception.reid import Embedder, TrackCrops, average_embedding, cut_crop, is_good_crop
from engine.perception.tracker import Tracker

log = logging.getLogger(__name__)


class EventSink(Protocol):
    """Where event calls go: the web queue (WebClient) or a file (offline mode)."""

    def send_event(self, payload: dict, snapshot: bytes | None = None, *, at: datetime | None = None) -> None: ...


@dataclass
class CameraRuntime:
    """Everything one camera needs while the engine runs."""

    camera: dict
    source: FrameSource | None
    tracker: Tracker
    modules: list[VisionModule]
    state_machine: StateMachine
    crops: TrackCrops
    mode: str = "live"  # "live" | "replay" | "offline"
    frame_index: int = 0
    fps: float = 0.0  # processing speed (frames per second)
    latency_ms: float = 0.0
    _last_done: float = 0.0
    pending_embeddings: dict = field(default_factory=dict)

    @property
    def camera_id(self) -> int:
        return int(self.camera["id"])

    @property
    def name(self) -> str:
        return str(self.camera.get("name", f"CAM-{self.camera_id}"))

    @property
    def online(self) -> bool:
        return True if self.source is None else self.source.is_online


@dataclass
class FrameResult:
    ctx: FrameContext
    actions: list[EventAction]


class Pipeline:
    def __init__(
        self,
        config: EngineConfig,
        detectors: dict[str, Detector],
        sink: EventSink,
        *,
        tracker_factory,
        embedder: Embedder | None = None,
    ):
        self.config = config
        self.detectors = detectors
        self.sink = sink
        self.tracker_factory = tracker_factory
        self.embedder = embedder
        self.gallery = RecentGallery(config.reid, config.events.merge_window_minutes)
        self.runtimes: dict[int, CameraRuntime] = {}

    # ------------------------------------------------------------------ cameras
    def add_camera(self, camera: dict, source: FrameSource | None, mode: str = "live") -> CameraRuntime:
        camera_id = int(camera["id"])
        keys = list(camera.get("modules") or MODULE_REGISTRY.keys() or [])
        if not keys:
            import engine.modules  # noqa: F401   (registers the built-in modules)

            keys = list(MODULE_REGISTRY)
        modules = create_modules(keys, self.config, camera_id)

        runtime = CameraRuntime(
            camera=camera,
            source=source,
            tracker=self.tracker_factory(),
            modules=modules,
            state_machine=None,
            crops=TrackCrops(self.config.reid.crops_per_track),
            mode=mode,
        )
        runtime.state_machine = StateMachine(
            camera_id, self.config.events, resolver=lambda obs, now, rt=runtime: self._resolve(rt, obs, now)
        )
        self.runtimes[camera_id] = runtime
        return runtime

    def remove_camera(self, camera_id: int, now: datetime) -> None:
        runtime = self.runtimes.pop(camera_id, None)
        if runtime is not None:
            self._handle(runtime, runtime.state_machine.close_all(now), None, now)
            if runtime.source is not None:
                runtime.source.stop()

    def close_all(self, now: datetime) -> None:
        """Engine is stopping: finish every open event."""
        for camera_id in list(self.runtimes):
            self.remove_camera(camera_id, now)

    # ------------------------------------------------------------------ one frame
    def process_frame(self, runtime: CameraRuntime, image, timestamp: datetime) -> FrameResult:
        started = time.perf_counter()
        ctx = FrameContext(runtime.camera_id, runtime.name, runtime.frame_index, timestamp, image)

        # 1) people, then their IDs
        person_detections = self.detectors["person"].detect([image])[0]
        ctx.persons = runtime.tracker.update(person_detections, image)

        # 2) the extra detectors the active modules need (only these are run)
        for name in sorted({d for module in runtime.modules for d in module.required_detectors}):
            ctx.detections[name] = self.detectors[name].detect([image])[0]

        # 3) modules say what they see
        for module in runtime.modules:
            for observation in module.process(ctx):
                observation.module = module.key
                ctx.observations.append(observation)

        # 4) keep crops of violating people for ReID, tell the gallery who is on screen
        self._collect_crops(runtime, ctx)
        alive = {t.track_id for t in ctx.persons}
        self.gallery.set_visible(runtime.camera_id, alive)
        runtime.crops.forget_except(alive | {o.track_id for o in ctx.observations if o.active})

        # 5) observations -> events
        actions = runtime.state_machine.process(timestamp, ctx.observations)
        self._handle(runtime, actions, ctx, timestamp)

        runtime.frame_index += 1
        self._update_stats(runtime, started)
        return FrameResult(ctx, actions)

    # ------------------------------------------------------------------ helpers
    def _collect_crops(self, runtime: CameraRuntime, ctx: FrameContext) -> None:
        if self.embedder is None or ctx.frame_index % self.config.reid.sample_every_frames:
            return
        height, width = ctx.image.shape[:2]
        for obs in ctx.observations:
            if not obs.active:
                continue
            others = [t.box for t in ctx.persons if t.track_id != obs.track_id]
            if is_good_crop((width, height), obs.box, others, self.config.reid.min_crop_height):
                runtime.crops.add(obs.track_id, cut_crop(ctx.image, obs.box))

    def _resolve(self, runtime: CameraRuntime, obs: Observation, now: datetime) -> MergeTarget | None:
        """The state machine asks: is this the same person as a recent violator?"""
        if self.embedder is None:
            return None
        crops = runtime.crops.get(obs.track_id)
        if not crops:
            return None
        embedding = average_embedding(self.embedder.embed(crops))
        runtime.pending_embeddings[(obs.module, obs.event_type, obs.track_id)] = embedding
        return self.gallery.find(runtime.camera_id, obs.module, obs.event_type, obs.track_id, embedding, now)

    def _handle(
        self, runtime: CameraRuntime, actions: list[EventAction], ctx: FrameContext | None, now: datetime
    ) -> None:
        for action in actions:
            embedding = runtime.pending_embeddings.pop((action.module, action.event_type, action.track_id), None)
            snapshot = None
            if action.kind == "create":
                if ctx is not None and action.box is not None:
                    snapshot = make_snapshot(ctx, action.track_id, action.box, action.labels, self.config)
                self.gallery.add(
                    action.uid, action.camera_id, action.module, action.event_type, action.track_id, embedding
                )
            elif action.kind == "reopen":
                self.gallery.reopen(action.uid, action.track_id, action.occurrences, embedding)
            else:
                self.gallery.close(action.uid, action.at)
            self.sink.send_event(to_payload(action), snapshot, at=now)
            log.info(
                "event %s %s %s track=%s camera=%s occurrences=%s",
                action.kind,
                action.event_type,
                action.uid[:8],
                action.track_id,
                action.camera_id,
                action.occurrences,
            )

    @staticmethod
    def _update_stats(runtime: CameraRuntime, started: float) -> None:
        done = time.perf_counter()
        latency = (done - started) * 1000
        runtime.latency_ms = latency if runtime.latency_ms == 0 else 0.9 * runtime.latency_ms + 0.1 * latency
        if runtime._last_done:
            gap = done - runtime._last_done
            if gap > 0:
                runtime.fps = 1 / gap if runtime.fps == 0 else 0.9 * runtime.fps + 0.1 / gap
        runtime._last_done = done

    # ------------------------------------------------------------------ status for the heartbeat
    def status(self) -> dict:
        return {
            "cameras": [
                {
                    "id": rt.camera_id,
                    "online": rt.online,
                    "fps": round(rt.fps, 1),
                    "latency_ms": round(rt.latency_ms, 1),
                    "mode": rt.mode,
                    "open_events": rt.state_machine.open_count,
                }
                for rt in self.runtimes.values()
            ]
        }
