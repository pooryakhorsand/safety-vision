"""
Event state machine: turns frame-by-frame Observations into a few clean events.
Generic: it knows nothing about helmets, it works for every module.

One "case" per (module, event_type, track):

    pending ──violation lasts confirm_seconds──────────────► open     (action: create, or reopen)
    pending ──violation gone > pending_grace_seconds───────► dropped  (it was only a flicker)
    open    ──no violation for clear_seconds / track lost──► ended    (action: end)
    ended   ──same track violates again, confirmed─────────► open     (action: reopen, same uid)
    ended   ──older than merge_window─────────────────────► dropped

When a case from a NEW track is confirmed, the `resolver` is asked first: "is this the same
person as a recent violator?" If yes, that earlier event is reopened (same uid) instead of
creating a new one, so one person who steps out and in again stays ONE event.

One StateMachine per camera.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime

from engine.core.config import EventsConfig
from engine.core.frame import Box, Label, Observation


@dataclass
class MergeTarget:
    """An earlier event of the same person, found by the recent-violators gallery."""

    uid: str
    occurrences: int
    track_ids: list[int]
    similarity: float


@dataclass
class EventAction:
    kind: str  # "create" | "reopen" | "end"
    uid: str
    camera_id: int
    module: str
    event_type: str
    track_id: int
    confidence: float
    at: datetime  # create/reopen: when the violation started; end: when it was last seen
    occurrences: int = 1
    track_ids: list[int] = field(default_factory=list)
    merged_similarity: float | None = None
    box: Box | None = None
    labels: list[Label] = field(default_factory=list)


Resolver = Callable[[Observation, datetime], MergeTarget | None]


@dataclass
class _Case:
    module: str
    event_type: str
    track_id: int
    state: str = "pending"  # pending | open | ended
    active_since: datetime | None = None
    last_active: datetime | None = None
    ended_at: datetime | None = None
    uid: str | None = None
    occurrences: int = 0
    track_ids: list[int] = field(default_factory=list)
    observation: Observation | None = None


class StateMachine:
    def __init__(self, camera_id: int, config: EventsConfig, resolver: Resolver | None = None):
        self.camera_id = camera_id
        self.config = config
        self.resolver = resolver
        self._cases: dict[tuple, _Case] = {}

    # ------------------------------------------------------------------ main step
    def process(self, now: datetime, observations: list[Observation]) -> list[EventAction]:
        actions: list[EventAction] = []
        active_keys = set()

        for obs in observations:
            if not obs.active:
                continue
            key = (obs.module, obs.event_type, obs.track_id)
            active_keys.add(key)
            case = self._cases.get(key)
            if case is None:
                case = self._cases[key] = _Case(obs.module, obs.event_type, obs.track_id, active_since=now)
            case.observation = obs
            case.last_active = now

            if case.state == "ended":  # the same person violates again
                case.state, case.active_since = "pending", now
            if case.state == "pending" and (now - case.active_since).total_seconds() >= self.config.confirm_seconds:
                actions.append(self._confirm(case, now))

        for key, case in list(self._cases.items()):
            if key in active_keys:
                continue
            gone_for = (now - case.last_active).total_seconds() if case.last_active else 0.0
            if case.state == "pending":
                if gone_for > self.config.pending_grace_seconds:
                    if case.uid:  # it was a re-violation that did not hold
                        case.state = "ended"
                    else:
                        del self._cases[key]
            elif case.state == "open":
                if gone_for >= self.config.clear_seconds:
                    actions.append(self._end(case))
            elif case.state == "ended":
                if (now - case.ended_at).total_seconds() > self.config.merge_window_minutes * 60:
                    del self._cases[key]
        return actions

    def close_all(self, now: datetime) -> list[EventAction]:
        """Engine is stopping: finish every open event so none stays open forever."""
        actions = [self._end(case) for case in self._cases.values() if case.state == "open"]
        self._cases.clear()
        return actions

    @property
    def open_count(self) -> int:
        return sum(1 for case in self._cases.values() if case.state == "open")

    # ------------------------------------------------------------------ transitions
    def _confirm(self, case: _Case, now: datetime) -> EventAction:
        obs = case.observation
        similarity = None
        if case.uid is None:
            target = self.resolver(obs, now) if self.resolver else None
            if target is not None:  # earlier event of the same person
                case.uid, case.occurrences = target.uid, target.occurrences
                case.track_ids, similarity = list(target.track_ids), target.similarity
        kind = "reopen" if case.uid else "create"
        if kind == "create":
            case.uid = str(uuid.uuid4())
        case.occurrences += 1
        if case.track_id not in case.track_ids:
            case.track_ids.append(case.track_id)
        case.state = "open"
        return EventAction(
            kind=kind,
            uid=case.uid,
            camera_id=self.camera_id,
            module=case.module,
            event_type=case.event_type,
            track_id=case.track_id,
            confidence=obs.confidence,
            at=case.active_since,
            occurrences=case.occurrences,
            track_ids=list(case.track_ids),
            merged_similarity=similarity,
            box=obs.box,
            labels=list(obs.labels),
        )

    def _end(self, case: _Case) -> EventAction:
        case.state, case.ended_at = "ended", case.last_active
        return EventAction(
            kind="end",
            uid=case.uid,
            camera_id=self.camera_id,
            module=case.module,
            event_type=case.event_type,
            track_id=case.track_id,
            confidence=case.observation.confidence if case.observation else 0.0,
            at=case.last_active,
            occurrences=case.occurrences,
            track_ids=list(case.track_ids),
        )


# ---------------------------------------------------------------------- API payload
def to_payload(action: EventAction) -> dict:
    """The JSON for POST /api/events/ (see docs/engine_api.md)."""
    if action.kind == "create":
        return {
            "uid": action.uid,
            "camera_id": action.camera_id,
            "module": action.module,
            "event_type": action.event_type,
            "started_at": action.at.isoformat(),
            "track_id": action.track_id,
            "confidence": round(action.confidence, 3),
            "occurrences": action.occurrences,
            "extra": {"track_ids": action.track_ids, "bbox": [round(v) for v in action.box] if action.box else None},
        }
    if action.kind == "reopen":
        extra = {"track_ids": action.track_ids}
        if action.merged_similarity is not None:
            extra["merged_similarity"] = round(action.merged_similarity, 3)
        return {
            "uid": action.uid,
            "ended_at": None,
            "occurrences": action.occurrences,
            "last_seen_at": action.at.isoformat(),
            "extra": extra,
        }
    return {"uid": action.uid, "ended_at": action.at.isoformat(), "last_seen_at": action.at.isoformat()}
