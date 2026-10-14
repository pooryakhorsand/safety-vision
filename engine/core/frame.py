"""
Plain data types that flow through the engine. No logic here.

One frame travels like this:
    source -> FrameContext(image) -> detectors/tracker fill persons + detections
           -> modules fill observations -> event state machine -> web
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

Box = tuple[float, float, float, float]  # x1, y1, x2, y2 in pixels of the original frame


@dataclass(frozen=True)
class Detection:
    """One box from a detector."""

    class_name: str
    confidence: float
    box: Box


@dataclass
class Track:
    """A person followed over time by the tracker."""

    track_id: int
    box: Box  # raw detection box, lightly smoothed
    confidence: float


@dataclass(frozen=True)
class Label:
    """One text on a person's tag, e.g. Label("no_helmet", True)."""

    name: str
    violation: bool


@dataclass
class Observation:
    """What a module sees right now about one person. Modules never keep events."""

    track_id: int
    event_type: str  # "no_helmet", "idle", ...
    active: bool  # True = the violation is present now
    confidence: float
    box: Box
    labels: list[Label] = field(default_factory=list)  # what to draw on the person's tag
    module: str = ""  # module key, filled by the pipeline ("ppe", ...)


@dataclass
class FrameContext:
    camera_id: int
    camera_name: str
    frame_index: int
    timestamp: datetime  # timezone-aware
    image: Any  # BGR numpy array, original resolution
    persons: list[Track] = field(default_factory=list)
    detections: dict[str, list[Detection]] = field(default_factory=dict)  # by detector name
    observations: list[Observation] = field(default_factory=list)
