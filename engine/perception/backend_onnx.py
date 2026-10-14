"""
Detector backend that runs an Ultralytics model exported to ONNX, with onnxruntime.

Export it with `python -m engine.tools.export_models` (writes <model>.onnx next to the .pt).
Class names are read from the ONNX metadata that Ultralytics writes during export.
The pre/post-processing is plain numpy so it can be tested without a GPU or a model.
"""

from __future__ import annotations

import ast
from collections.abc import Sequence

import numpy as np

from engine.core.config import DetectorConfig, DeviceConfig, resolve_path
from engine.core.frame import Detection
from engine.perception.detector import Detector


def letterbox(image, size: int):
    """Resize keeping the aspect ratio, pad with grey to size x size. Returns (blob, scale, pad_x, pad_y)."""
    import cv2

    h, w = image.shape[:2]
    scale = min(size / h, size / w)
    new_w, new_h = int(round(w * scale)), int(round(h * scale))
    resized = cv2.resize(image, (new_w, new_h), interpolation=cv2.INTER_LINEAR)
    pad_x, pad_y = (size - new_w) // 2, (size - new_h) // 2
    canvas = np.full((size, size, 3), 114, dtype=np.uint8)
    canvas[pad_y : pad_y + new_h, pad_x : pad_x + new_w] = resized
    blob = canvas[:, :, ::-1].transpose(2, 0, 1).astype(np.float32) / 255.0  # BGR -> RGB, HWC -> CHW
    return blob, scale, pad_x, pad_y


def decode(
    output: np.ndarray, names: dict, config: DetectorConfig, scale: float, pad_x: int, pad_y: int, image_shape: tuple
) -> list[Detection]:
    """
    Turn one YOLO output [4 + classes, boxes] (centre x/y, w, h, class scores) into detections.
    Applies the confidence threshold, the class filter and NMS (per class unless agnostic_nms).
    """
    import cv2

    predictions = output.T  # [boxes, 4 + classes]
    scores_all = predictions[:, 4:]
    class_ids = scores_all.argmax(axis=1)
    scores = scores_all[np.arange(len(scores_all)), class_ids]

    keep = scores >= config.conf
    if config.classes:
        keep &= np.isin(class_ids, list(config.classes))
    predictions, class_ids, scores = predictions[keep], class_ids[keep], scores[keep]
    if not len(scores):
        return []

    cx, cy, w, h = predictions[:, 0], predictions[:, 1], predictions[:, 2], predictions[:, 3]
    x1 = (cx - w / 2 - pad_x) / scale
    y1 = (cy - h / 2 - pad_y) / scale
    x2 = (cx + w / 2 - pad_x) / scale
    y2 = (cy + h / 2 - pad_y) / scale
    height, width = image_shape[:2]
    x1, x2 = np.clip(x1, 0, width), np.clip(x2, 0, width)
    y1, y2 = np.clip(y1, 0, height), np.clip(y2, 0, height)

    # NMS: offset boxes by class id so different classes never suppress each other.
    offset = np.zeros_like(class_ids, dtype=np.float32) if config.agnostic_nms else class_ids.astype(np.float32) * 10000
    boxes_for_nms = [
        [float(a + o), float(b + o), float(c - a), float(d - b)] for a, b, c, d, o in zip(x1, y1, x2, y2, offset)
    ]
    kept = cv2.dnn.NMSBoxes(boxes_for_nms, scores.astype(float).tolist(), config.conf, config.iou)

    detections = []
    for i in np.array(kept).reshape(-1):
        detections.append(
            Detection(
                names.get(int(class_ids[i]), str(class_ids[i])),
                float(scores[i]),
                (float(x1[i]), float(y1[i]), float(x2[i]), float(y2[i])),
            )
        )
    return detections


class OnnxDetector(Detector):
    def __init__(self, name: str, config: DetectorConfig, device: DeviceConfig):
        import onnxruntime as ort

        self.name = name
        self.config = config
        use_gpu = str(device.gpu).strip().lower() != "cpu" and "CUDAExecutionProvider" in ort.get_available_providers()
        providers = ["CUDAExecutionProvider", "CPUExecutionProvider"] if use_gpu else ["CPUExecutionProvider"]
        path = resolve_path(config.weights)
        if not path.exists():
            raise FileNotFoundError(f"ONNX model not found: {path} (create it with engine.tools.export_models)")
        self.session = ort.InferenceSession(str(path), providers=providers)
        self.input_name = self.session.get_inputs()[0].name
        fixed = self.session.get_inputs()[0].shape[-1]
        self.size = int(fixed) if isinstance(fixed, int) else int(config.imgsz)  # fixed export size wins
        self.names = self._read_names()

    def _read_names(self) -> dict:
        raw = (self.session.get_modelmeta().custom_metadata_map or {}).get("names")
        if raw:
            try:
                return {int(k): str(v) for k, v in ast.literal_eval(raw).items()}
            except (ValueError, SyntaxError):
                pass
        return {}

    def detect(self, images: Sequence) -> list[list[Detection]]:
        results = []
        for image in images:  # batch of 1 per run: exported models are static-shape
            blob, scale, pad_x, pad_y = letterbox(image, self.size)
            output = self.session.run(None, {self.input_name: blob[None]})[0][0]
            results.append(decode(output, self.names, self.config, scale, pad_x, pad_y, image.shape))
        return results
