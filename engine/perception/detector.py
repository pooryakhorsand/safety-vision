"""
Detector interface. Every backend (PyTorch, ONNX, TensorRT) looks the same to the rest of the engine:

    detections = detector.detect([image1, image2])   # one list of Detection per image

"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence

from engine.core.config import DetectorConfig, DeviceConfig
from engine.core.frame import Detection


class Detector(ABC):
    name: str = "detector"

    @abstractmethod
    def detect(self, images: Sequence) -> list[list[Detection]]:
        """Run on a batch of BGR images; return one list of detections per image."""


def resolve_device(device: DeviceConfig):
    """GPU index or "cpu". Falls back to CPU (with a warning) when CUDA is not available."""
    import logging

    wanted = str(device.gpu).strip().lower()
    if wanted == "cpu":
        return "cpu"
    try:
        import torch

        if torch.cuda.is_available():
            return int(wanted)
        logging.getLogger(__name__).warning("CUDA is not available, running on CPU (slow)")
    except ImportError:
        logging.getLogger(__name__).warning("PyTorch is not installed, running on CPU")
    return "cpu"


def build_detector(name: str, config: DetectorConfig, device: DeviceConfig) -> Detector:
    """Create the backend named in the settings (detectors.<name>.backend)."""
    if config.backend == "ultralytics":
        from engine.perception.backend_ultralytics import UltralyticsDetector

        return UltralyticsDetector(name, config, device)
    if config.backend == "onnx":
        from engine.perception.backend_onnx import OnnxDetector

        return OnnxDetector(name, config, device)
    if config.backend == "tensorrt":
        # Ultralytics loads a TensorRT .engine file itself, so the same wrapper works.
        from engine.perception.backend_ultralytics import UltralyticsDetector

        return UltralyticsDetector(name, config, device)
    raise ValueError(f"unknown detector backend '{config.backend}'")
