"""Test helpers. Not part of the engine: tests use these so they run without a GPU or model files."""

from __future__ import annotations

from collections.abc import Callable, Sequence

from engine.core.frame import Detection
from engine.perception.detector import Detector


class ScriptedDetector(Detector):
    """
    Replays boxes. `script` is either
      - a list: script[i] is the list of Detection for the i-th image seen, or
      - a function (image_number, image) -> list[Detection].
    After the list ends it returns nothing.
    """

    def __init__(
        self, script: Sequence[list[Detection]] | Callable[[int, object], list[Detection]], name: str = "scripted"
    ):
        self.name = name
        self._script = script
        self.images_seen = 0

    def detect(self, images: Sequence) -> list[list[Detection]]:
        results = []
        for image in images:
            n = self.images_seen
            self.images_seen += 1
            if callable(self._script):
                results.append(list(self._script(n, image)))
            else:
                results.append(list(self._script[n]) if n < len(self._script) else [])
        return results
