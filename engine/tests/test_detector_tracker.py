import numpy as np

from engine.perception.detector import build_detector
from engine.perception.tracker import BoxSmoother, IouTracker, iou
from engine.tests.conftest import det, make_config
from engine.tests.fakes import ScriptedDetector


def test_fake_detector_replays_a_list_and_then_stops():
    detector = ScriptedDetector([[det("person", (0, 0, 10, 10))], []])
    image = np.zeros((10, 10, 3), np.uint8)
    out = detector.detect([image, image, image])
    assert [len(x) for x in out] == [1, 0, 0]
    assert detector.images_seen == 3


def test_fake_detector_with_function():
    detector = ScriptedDetector(lambda n, image: [det("person", (n, 0, n + 5, 5))])
    out = detector.detect([None, None])
    assert out[1][0].box[0] == 1.0


def test_unknown_backend_is_explained():
    cfg = make_config()
    cfg.detectors.person.backend = "onnx"
    try:
        build_detector("person", cfg.detectors.person, cfg.device)
    except (FileNotFoundError, ImportError) as error:  # no model file / onnxruntime missing: says what to do
        assert "onnx" in str(error).lower()


def test_slowly_moving_person_keeps_one_id():
    tracker = IouTracker(make_config().tracker)
    ids = set()
    for i in range(30):
        tracks = tracker.update([det("person", (100 + i * 3, 50, 200 + i * 3, 300))], None)
        ids.add(tracks[0].track_id)
    assert ids == {1}


def test_two_people_get_two_ids_and_new_person_gets_new_id():
    tracker = IouTracker(make_config().tracker)
    a, b = det("person", (10, 10, 100, 300)), det("person", (400, 10, 490, 300))
    first = tracker.update([a, b], None)
    second = tracker.update([a, b], None)
    assert {t.track_id for t in first} == {t.track_id for t in second} and len(first) == 2
    third = tracker.update([a, b, det("person", (200, 10, 290, 300))], None)
    assert len({t.track_id for t in third}) == 3


def test_track_is_forgotten_after_buffer_and_gets_new_id():
    cfg = make_config()
    cfg.tracker.track_buffer = 3
    tracker = IouTracker(cfg.tracker)
    box = det("person", (100, 50, 200, 300))
    first = tracker.update([box], None)[0].track_id
    for _ in range(6):
        tracker.update([], None)
    assert tracker.update([box], None)[0].track_id != first


def test_smoothing_and_iou():
    smoother = BoxSmoother(0.5)
    smoother.smooth(1, (0, 0, 10, 10))
    assert smoother.smooth(1, (10, 10, 20, 20)) == (5.0, 5.0, 15.0, 15.0)
    assert iou((0, 0, 10, 10), (0, 0, 10, 10)) == 1.0
    assert iou((0, 0, 10, 10), (20, 20, 30, 30)) == 0.0
