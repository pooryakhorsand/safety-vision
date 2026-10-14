"""
Person tracker: gives every person an ID that stays the same from frame to frame.

Two implementations, same interface:
  BotSortTracker   production: BoxMOT BoT-SORT (+ ReID appearance)
  IouTracker       tiny and dependency-free: tests, CI, and a fallback

We draw/measure the RAW detection box, not the tracker's Kalman prediction
(the prediction lags behind moving people), then smooth it a little.
"""

from __future__ import annotations

import inspect
from abc import ABC, abstractmethod
from collections.abc import Sequence
from pathlib import Path

import numpy as np

from engine.core.config import DeviceConfig, TrackerConfig, resolve_path
from engine.core.frame import Box, Detection, Track


def iou(a: Box, b: Box) -> float:
    iw = min(a[2], b[2]) - max(a[0], b[0])
    ih = min(a[3], b[3]) - max(a[1], b[1])
    if iw <= 0 or ih <= 0:
        return 0.0
    inter = iw * ih
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


class BoxSmoother:
    """Exponential smoothing of each track's box. alpha=1 means no smoothing."""

    def __init__(self, alpha: float):
        self.alpha = alpha
        self._boxes: dict[int, np.ndarray] = {}
        self._last_seen: dict[int, int] = {}
        self._tick = 0

    def smooth(self, track_id: int, box: Box) -> Box:
        new = np.asarray(box, dtype=np.float32)
        old = self._boxes.get(track_id)
        if old is not None:
            new = self.alpha * new + (1 - self.alpha) * old
        self._boxes[track_id] = new
        self._last_seen[track_id] = self._tick
        return tuple(float(v) for v in new)

    def end_frame(self) -> None:
        """Forget tracks not seen for a long time so the dictionaries do not grow forever."""
        self._tick += 1
        if self._tick % 300 == 0:
            for track_id in [t for t, seen in self._last_seen.items() if self._tick - seen > 300]:
                self._boxes.pop(track_id, None)
                self._last_seen.pop(track_id, None)


class Tracker(ABC):
    @abstractmethod
    def update(self, detections: Sequence[Detection], image) -> list[Track]:
        """One frame in, the currently visible tracks out."""


class IouTracker(Tracker):
    """Greedy matching by overlap. Good enough for tests and slow-moving scenes."""

    def __init__(self, config: TrackerConfig, min_iou: float = 0.3):
        self.min_iou = min_iou
        self.max_age = config.track_buffer
        self.smoother = BoxSmoother(config.box_smooth)
        self._next_id = 1
        self._tracks: dict[int, dict] = {}  # id -> {"box", "age"}

    def update(self, detections: Sequence[Detection], image=None) -> list[Track]:
        pairs = sorted(
            ((iou(d.box, t["box"]), di, tid) for di, d in enumerate(detections) for tid, t in self._tracks.items()),
            reverse=True,
        )
        det_to_track: dict[int, int] = {}
        used: set[int] = set()
        for score, di, tid in pairs:
            if score < self.min_iou:
                break
            if di in det_to_track or tid in used:
                continue
            det_to_track[di] = tid
            used.add(tid)

        for tid, track in self._tracks.items():
            track["age"] = 0 if tid in used else track["age"] + 1

        output = []
        for di, det in enumerate(detections):
            tid = det_to_track.get(di)
            if tid is None:
                tid = self._next_id
                self._next_id += 1
                self._tracks[tid] = {"box": det.box, "age": 0}
            self._tracks[tid]["box"] = det.box
            output.append(Track(tid, self.smoother.smooth(tid, det.box), det.confidence))

        for tid in [t for t, tr in self._tracks.items() if tr["age"] > self.max_age]:
            del self._tracks[tid]
        self.smoother.end_frame()
        return output


class BotSortTracker(Tracker):
    """BoT-SORT from BoxMOT. Rows it returns: x1, y1, x2, y2, id, conf, cls, detection_index."""

    def __init__(self, config: TrackerConfig, device: DeviceConfig):
        import torch
        from boxmot import BotSort  # heavy import: only when this tracker is used

        from engine.perception.detector import resolve_device

        gpu = resolve_device(device)
        wanted = dict(
            reid_weights=Path(resolve_path(config.reid_weights)),
            device=torch.device("cpu" if gpu == "cpu" else f"cuda:{gpu}"),
            half=bool(device.half) and gpu != "cpu",
            with_reid=config.with_reid,
            track_buffer=config.track_buffer,
        )
        # BoxMOT versions differ: pass only the arguments this version knows.
        accepted = inspect.signature(BotSort.__init__).parameters
        if "with_reid" not in accepted and "use_embeddings" in accepted:  # newer name of the same switch
            wanted["use_embeddings"] = wanted.pop("with_reid")
        self.tracker = BotSort(**{k: v for k, v in wanted.items() if k in accepted})
        self.smoother = BoxSmoother(config.box_smooth)

    def update(self, detections: Sequence[Detection], image) -> list[Track]:
        if detections:
            rows = np.array([[*d.box, d.confidence, 0.0] for d in detections], dtype=np.float32)
        else:
            rows = np.empty((0, 6), dtype=np.float32)
        tracked = self.tracker.update(rows, image)

        output = []
        for row in tracked:
            track_id = int(row[4])
            det_index = int(row[7]) if len(row) > 7 else -1
            if 0 <= det_index < len(detections):
                box = detections[det_index].box  # raw detection box
                conf = detections[det_index].confidence
            else:
                box = tuple(float(v) for v in row[:4])  # fall back to the tracker's own box
                conf = float(row[5])
            output.append(Track(track_id, self.smoother.smooth(track_id, box), conf))
        self.smoother.end_frame()
        return output


def build_tracker(config: TrackerConfig, device: DeviceConfig) -> Tracker:
    """One tracker per camera (each keeps its own IDs)."""
    if config.type == "iou":
        return IouTracker(config)
    return BotSortTracker(config, device)
