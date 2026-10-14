"""ONNX pre/post-processing and the small tool helpers (no model, no GPU)."""

import numpy as np

from engine.core.config import DetectorConfig
from engine.core.frame import Detection
from engine.perception.backend_onnx import decode, letterbox
from engine.perception.detector import build_detector
from engine.tools.benchmark import summarize
from engine.tools.check_parity import compare


def test_letterbox_shape_and_scale():
    image = np.zeros((360, 640, 3), dtype=np.uint8)
    blob, scale, pad_x, pad_y = letterbox(image, 640)
    assert blob.shape == (3, 640, 640)
    assert scale == 1.0 and pad_x == 0 and pad_y == 140


def make_output(rows):
    """rows: (cx, cy, w, h, score_class0, score_class1) -> array [4 + 2, boxes]."""
    return np.array(rows, dtype=np.float32).T


def test_decode_maps_back_to_image_and_filters():
    config = DetectorConfig(weights="x", conf=0.3, iou=0.5)
    # Image 1280x720 letterboxed into 640: scale 0.5, pad_y 140.
    output = make_output(
        [
            (320, 320, 100, 200, 0.9, 0.0),  # person-like box, class 0
            (322, 322, 100, 200, 0.8, 0.0),  # duplicate -> removed by NMS
            (100, 100, 20, 20, 0.1, 0.0),  # below conf
            (500, 300, 50, 50, 0.0, 0.7),  # class 1
        ]
    )
    found = decode(output, {0: "person", 1: "helmet"}, config, 0.5, 0, 140, (720, 1280, 3))
    assert sorted(d.class_name for d in found) == ["helmet", "person"]
    person = next(d for d in found if d.class_name == "person")
    assert person.box == (540.0, 160.0, 740.0, 560.0)


def test_decode_class_filter_and_empty():
    config = DetectorConfig(weights="x", conf=0.3, classes=[1])
    output = make_output([(320, 320, 100, 200, 0.9, 0.0), (500, 300, 50, 50, 0.0, 0.7)])
    found = decode(output, {0: "person", 1: "helmet"}, config, 1.0, 0, 0, (640, 640, 3))
    assert [d.class_name for d in found] == ["helmet"]
    assert decode(make_output([(1, 1, 1, 1, 0.0, 0.0)]), {}, config, 1.0, 0, 0, (640, 640, 3)) == []


def test_build_detector_unknown_backend():
    import pytest

    with pytest.raises(ValueError):
        build_detector("x", DetectorConfig(weights="x", backend="nope"), None)


def test_compare_matches_by_class_and_iou():
    ref = [Detection("person", 0.9, (0, 0, 100, 200)), Detection("person", 0.8, (300, 0, 400, 200))]
    cand = [Detection("person", 0.88, (2, 0, 101, 199)), Detection("helmet", 0.9, (300, 0, 400, 200))]
    matched, total, diffs = compare(ref, cand)
    assert (matched, total) == (1, 2)
    assert abs(diffs[0] - 0.02) < 1e-6


def test_summarize_latencies():
    result = summarize([10.0, 10.0, 20.0, 20.0])
    assert result["frames"] == 4 and result["mean_ms"] == 15.0 and round(result["fps"], 2) == 66.67
