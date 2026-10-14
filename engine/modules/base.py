"""
Module interface.

A module looks at ONE frame (persons + detections) and reports what it sees right now
as Observations. It never sends anything to the web, never draws, never creates events:
the shared event state machine turns observations into events.

To add a module:
  1. create modules/<key>/module.py with a class that extends VisionModule
  2. decorate it with @register_module and import it in modules/__init__.py
  3. declare the same key and event types in web/apps/vision_modules/registry.py
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod

from engine.core.config import EngineConfig
from engine.core.frame import FrameContext, Observation

log = logging.getLogger(__name__)

MODULE_REGISTRY: dict[str, type["VisionModule"]] = {}


class VisionModule(ABC):
    key: str = ""  # same key as in the web registry
    required_detectors: tuple[str, ...] = ()  # extra detectors it needs, e.g. ("equipment",)

    def __init__(self, config: EngineConfig, camera_id: int):
        self.config = config
        self.camera_id = camera_id

    @abstractmethod
    def process(self, ctx: FrameContext) -> list[Observation]:
        """Look at one frame and return observations (module keeps only what it needs between frames)."""


def register_module(cls: type[VisionModule]) -> type[VisionModule]:
    if not cls.key:
        raise ValueError(f"{cls.__name__} has no key")
    MODULE_REGISTRY[cls.key] = cls
    return cls


def create_modules(keys: list[str], config: EngineConfig, camera_id: int) -> list[VisionModule]:
    """Build the modules a camera asked for. Unknown keys are skipped with a warning."""
    import engine.modules  # noqa: F401  (importing the package registers the built-in modules)

    modules = []
    for key in keys:
        cls = MODULE_REGISTRY.get(key)
        if cls is None:
            log.warning("camera %s asks for module '%s' which this engine does not have; skipped", camera_id, key)
            continue
        modules.append(cls(config, camera_id))
    return modules
