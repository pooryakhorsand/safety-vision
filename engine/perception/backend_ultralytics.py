"""Detector backend that runs an Ultralytics YOLO .pt model with PyTorch."""

from __future__ import annotations

from collections.abc import Sequence

from engine.core.config import DetectorConfig, DeviceConfig, resolve_path
from engine.core.frame import Detection
from engine.perception.detector import Detector, resolve_device


class UltralyticsDetector(Detector):
    def __init__(self, name: str, config: DetectorConfig, device: DeviceConfig):
        from ultralytics import YOLO  # heavy import: only when this backend is used

        self.name = name
        self.config = config
        self.device = resolve_device(device)
        self.half = bool(device.half) and self.device != "cpu"

        weights = resolve_path(config.weights)
        # A bare name like "yolo11x.pt" lets Ultralytics download it; a path must exist.
        source = str(weights) if weights.exists() else config.weights
        self.model = YOLO(source)
        self.names = self.model.names

    def detect(self, images: Sequence) -> list[list[Detection]]:
        if not len(images):
            return []
        cfg = self.config
        results = self.model.predict(
            list(images),
            device=self.device,
            imgsz=cfg.imgsz,
            conf=cfg.conf,
            iou=cfg.iou,
            agnostic_nms=cfg.agnostic_nms,
            classes=list(cfg.classes) or None,
            half=self.half,
            verbose=False,
        )
        output = []
        for result in results:
            detections = []
            if len(result.boxes):
                xyxy = result.boxes.xyxy.cpu().numpy()
                conf = result.boxes.conf.cpu().numpy()
                cls = result.boxes.cls.cpu().numpy().astype(int)
                for box, c, k in zip(xyxy, conf, cls):
                    detections.append(Detection(self.names[int(k)], float(c), tuple(float(v) for v in box)))
            output.append(detections)
        return output
