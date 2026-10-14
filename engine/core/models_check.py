"""Checks that the model files named in engine.yaml exist, so a missing file gives a clear message."""

from __future__ import annotations

from pathlib import Path

from engine.core.config import EngineConfig, resolve_path


def missing_models(config: EngineConfig) -> list[dict]:
    """Return [{"key": "detectors.equipment.weights", "path": "..."}] for every model file that is not there.

    A bare file name such as ``yolo11x.pt`` is left alone: Ultralytics downloads it on first use.
    """
    missing = []
    for name in ("person", "equipment"):
        detector = getattr(config.detectors, name)
        if len(Path(detector.weights).parts) == 1 and detector.backend == "ultralytics":
            continue
        path = resolve_path(detector.weights)
        if not path.exists():
            missing.append({"key": f"detectors.{name}.weights", "path": str(path)})
    return missing


def describe(missing: list[dict]) -> str:
    lines = ["Model file(s) not found:"]
    lines += [f"  - {item['path']}   (setting: {item['key']})" for item in missing]
    lines.append("General models: python -m engine.tools.download_models. Your own PPE model: see docs/models.md.")
    return "\n".join(lines)
