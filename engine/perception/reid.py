"""
ReID embedder: person crop -> a vector that is similar for the same person.

Used ONLY to merge repeat violations of one person within minutes (see identity/recent_gallery.py),
where clothing does not change. It is not used to give people names.

  BoxmotEmbedder     OSNet through BoxMOT (production)
  HistogramEmbedder  colour layout of head / torso / legs: no model, weak, for tests and as a fallback
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from collections import defaultdict, deque
from collections.abc import Sequence
from pathlib import Path

import cv2
import numpy as np

from engine.core.config import DeviceConfig, ReidConfig, resolve_path
from engine.core.frame import Box

log = logging.getLogger(__name__)


def normalize(vectors: np.ndarray) -> np.ndarray:
    vectors = np.atleast_2d(np.asarray(vectors, dtype=np.float32))
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    return vectors / np.maximum(norms, 1e-12)


def average_embedding(vectors: np.ndarray) -> np.ndarray:
    """Mean of several embeddings of the same person, L2-normalized again."""
    return normalize(np.mean(normalize(vectors), axis=0))[0]


class Embedder(ABC):
    @abstractmethod
    def embed(self, crops: Sequence[np.ndarray]) -> np.ndarray:
        """N BGR crops in, N x D L2-normalized vectors out."""


class HistogramEmbedder(Embedder):
    """HSV colour histogram of three horizontal stripes. Cheap and weak, but needs nothing."""

    def embed(self, crops: Sequence[np.ndarray]) -> np.ndarray:
        vectors = []
        for crop in crops:
            hsv = cv2.cvtColor(cv2.resize(crop, (32, 96)), cv2.COLOR_BGR2HSV)
            parts = []
            for stripe in np.array_split(hsv, 3, axis=0):
                hist = cv2.calcHist([stripe], [0, 1, 2], None, [8, 4, 4], [0, 180, 0, 256, 0, 256]).flatten()
                parts.append(np.sqrt(hist / max(hist.sum(), 1.0)))
            vectors.append(np.concatenate(parts))
        return normalize(np.array(vectors))


class BoxmotEmbedder(Embedder):
    """OSNet through BoxMOT's ReID backend (the same weights file the tracker uses)."""

    def __init__(self, weights: Path, device: DeviceConfig):
        import torch

        from engine.perception.detector import resolve_device

        backend_class = _find_boxmot_backend()
        gpu = resolve_device(device)
        torch_device = torch.device("cpu" if gpu == "cpu" else f"cuda:{gpu}")
        self.model = backend_class(weights=Path(weights), device=torch_device, half=False).model

    def embed(self, crops: Sequence[np.ndarray]) -> np.ndarray:
        vectors = []
        for crop in crops:
            height, width = crop.shape[:2]
            boxes = np.array([[0, 0, width, height]], dtype=np.float32)
            features = self.model.get_features(boxes, crop)
            vectors.append(np.asarray(features, dtype=np.float32).reshape(-1))
        return normalize(np.array(vectors))


def _find_boxmot_backend():
    """BoxMOT moved this class between versions: try the known places."""
    for module_name in ("boxmot.appearance.reid.auto_backend", "boxmot.appearance.reid_auto_backend"):
        try:
            module = __import__(module_name, fromlist=["ReidAutoBackend"])
            return module.ReidAutoBackend
        except (ImportError, AttributeError):
            continue
    raise ImportError(
        "this BoxMOT version has no ReidAutoBackend (found in BoxMOT 10-16). "
        "Install a version that has it, or set reid.backend: histogram"
    )


def build_embedder(config: ReidConfig, device: DeviceConfig) -> Embedder:
    if config.backend == "histogram":
        return HistogramEmbedder()
    weights = resolve_path(config.weights)
    try:
        return BoxmotEmbedder(weights, device)
    except Exception as error:  # missing package, weights, or unsupported BoxMOT version
        log.warning(
            "OSNet ReID is not available (%s). Using the weak histogram embedder instead; "
            "repeat-violation merging will be less reliable.",
            error,
        )
        return HistogramEmbedder()


# ----------------------------------------------------------------------- crops
def is_good_crop(
    frame_size: tuple[int, int],
    box: Box,
    other_boxes: Sequence[Box],
    min_height: int,
    border: int = 2,
    max_overlap: float = 0.3,
) -> bool:
    """
    A crop is good for ReID when the person is big enough, not cut by the frame edge,
    and not covered by another person.  frame_size = (width, height).
    """
    width, height = frame_size
    x1, y1, x2, y2 = box
    if y2 - y1 < min_height:
        return False
    if x1 < border or y1 < border or x2 > width - border or y2 > height - border:
        return False
    for other in other_boxes:
        iw = min(x2, other[2]) - max(x1, other[0])
        ih = min(y2, other[3]) - max(y1, other[1])
        if iw > 0 and ih > 0:
            inter = iw * ih
            union = (x2 - x1) * (y2 - y1) + (other[2] - other[0]) * (other[3] - other[1]) - inter
            if inter / union >= max_overlap:
                return False
    return True


def cut_crop(image, box: Box):
    x1, y1, x2, y2 = (int(round(v)) for v in box)
    return image[max(0, y1) : y2, max(0, x1) : x2].copy()


class TrackCrops:
    """The last few good crops of each person (kept only while they violate)."""

    def __init__(self, per_track: int):
        self._crops: dict[int, deque] = defaultdict(lambda: deque(maxlen=per_track))

    def add(self, track_id: int, crop) -> None:
        self._crops[track_id].append(crop)

    def get(self, track_id: int) -> list:
        return list(self._crops.get(track_id, []))

    def forget_except(self, alive_ids: set[int]) -> None:
        for track_id in [t for t in self._crops if t not in alive_ids]:
            del self._crops[track_id]
