"""
Recent violators: the "one person, 20 events" fix.

When a violation is about to become a NEW event, the pipeline asks this gallery: "is this the
same person as someone who violated the same rule a few minutes ago?" If yes, the earlier event
is reopened instead of creating another one.

Rules
  - same module and event type
  - same camera, or a camera listed in reid.neighbor_cameras
  - the earlier event ended less than merge_window_minutes ago (or is still open)
  - never two people visible at the same time: an earlier entry whose track is on screen right
    now is a different person
  - cosine similarity of the ReID vectors >= reid.merge_threshold

Memory only. Nothing about people is written to disk.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

import numpy as np

from engine.core.config import ReidConfig
from engine.events.state_machine import MergeTarget


@dataclass
class GalleryEntry:
    uid: str
    camera_id: int
    module: str
    event_type: str
    track_id: int
    templates: list[np.ndarray] = field(default_factory=list)
    occurrences: int = 1
    track_ids: list[int] = field(default_factory=list)
    closed_at: datetime | None = None  # None = the event is still open


class RecentGallery:
    def __init__(self, config: ReidConfig, merge_window_minutes: float):
        self.config = config
        self.window_seconds = merge_window_minutes * 60
        self._entries: dict[str, GalleryEntry] = {}
        self._visible: dict[int, set[int]] = {}

    def __len__(self) -> int:
        return len(self._entries)

    # ------------------------------------------------------------ updates from the pipeline
    def set_visible(self, camera_id: int, track_ids: set[int]) -> None:
        """Which tracks are on screen right now on this camera (call every frame)."""
        self._visible[camera_id] = set(track_ids)

    def add(
        self, uid: str, camera_id: int, module: str, event_type: str, track_id: int, embedding: np.ndarray | None
    ) -> None:
        entry = GalleryEntry(uid, camera_id, module, event_type, track_id, track_ids=[track_id])
        if embedding is not None:
            entry.templates.append(np.asarray(embedding, dtype=np.float32))
        self._entries[uid] = entry

    def reopen(self, uid: str, track_id: int, occurrences: int, embedding: np.ndarray | None) -> None:
        entry = self._entries.get(uid)
        if entry is None:
            return
        entry.closed_at, entry.track_id, entry.occurrences = None, track_id, occurrences
        if track_id not in entry.track_ids:
            entry.track_ids.append(track_id)
        if embedding is not None:
            entry.templates.append(np.asarray(embedding, dtype=np.float32))
            del entry.templates[: -self.config.max_templates]  # keep only the newest

    def close(self, uid: str, at: datetime) -> None:
        entry = self._entries.get(uid)
        if entry is not None:
            entry.closed_at = at

    def expire(self, now: datetime) -> None:
        for uid in [
            u
            for u, e in self._entries.items()
            if e.closed_at is not None and (now - e.closed_at).total_seconds() > self.window_seconds
        ]:
            del self._entries[uid]

    # ------------------------------------------------------------ the question
    def find(
        self, camera_id: int, module: str, event_type: str, track_id: int, embedding: np.ndarray, now: datetime
    ) -> MergeTarget | None:
        self.expire(now)
        allowed = self._allowed_cameras(camera_id)
        query = np.asarray(embedding, dtype=np.float32)

        best_entry, best_similarity = None, -1.0
        for entry in self._entries.values():
            if entry.module != module or entry.event_type != event_type or entry.camera_id not in allowed:
                continue
            if not entry.templates:
                continue
            own_track = entry.camera_id == camera_id and entry.track_id == track_id
            if not own_track and entry.track_id in self._visible.get(entry.camera_id, set()):
                continue  # on screen now => a different person
            similarity = float(np.max(np.stack(entry.templates) @ query))
            if similarity > best_similarity:
                best_entry, best_similarity = entry, similarity

        if best_entry is None or best_similarity < self.config.merge_threshold:
            return None
        return MergeTarget(best_entry.uid, best_entry.occurrences, list(best_entry.track_ids), best_similarity)

    def _allowed_cameras(self, camera_id: int) -> set[int]:
        neighbors = self.config.neighbor_cameras
        listed = neighbors.get(camera_id, neighbors.get(str(camera_id), []))
        return {camera_id, *(int(c) for c in listed)}
