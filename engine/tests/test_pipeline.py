"""End-to-end: fake detectors + real tracker/modules/state machine/gallery/snapshot. No GPU needed."""

import cv2
import numpy as np

from engine.core.pipeline import Pipeline
from engine.perception.reid import HistogramEmbedder
from engine.perception.tracker import IouTracker
from engine.tests.conftest import CollectingSink, at, det, make_config, scene
from engine.tests.fakes import ScriptedDetector

RED, BLUE = (0, 0, 255), (255, 0, 0)


class Scene:
    """The test describes who is on screen; the fake detectors read it."""

    def __init__(self):
        self.people = []  # (box, colour, wearing_helmet)
        self.config = make_config()
        self.sink = CollectingSink()
        person = ScriptedDetector(lambda n, img: [det("person", box) for box, _, _ in self.people])
        equipment = ScriptedDetector(
            lambda n, img: [
                det("helmet" if helmet else "no_helmet", (box[0] + 30, box[1], box[2] - 30, box[1] + 40))
                for box, _, helmet in self.people
            ]
        )
        self.pipeline = Pipeline(
            self.config,
            {"person": person, "equipment": equipment},
            self.sink,
            tracker_factory=lambda: IouTracker(self.config.tracker),
            embedder=HistogramEmbedder(),
        )
        self.runtime = self.pipeline.add_camera({"id": 1, "name": "CAM-01", "modules": ["ppe"]}, None)
        self.clock = 0.0

    def run(self, seconds, people):
        self.people = people
        steps = int(round(seconds * 10))
        for _ in range(steps):
            image = scene([(box, colour) for box, colour, _ in people])
            self.pipeline.process_frame(self.runtime, image, at(self.clock))
            self.clock += 0.1

    def jump(self, seconds):
        self.clock += seconds

    @property
    def kinds(self):
        return [
            "create" if "event_type" in p else ("end" if p.get("ended_at") else "reopen") for p in self.sink.payloads
        ]


A = (100, 50, 220, 400)
B = (350, 60, 470, 410)


def test_violation_becomes_one_event_with_a_snapshot_and_ends():
    s = Scene()
    s.run(3, [(A, RED, False)])
    s.run(2, [])
    assert s.kinds == ["create", "end"]
    create, snapshot = s.sink.calls[0]
    assert create["event_type"] == "no_helmet" and create["module"] == "ppe" and create["camera_id"] == 1
    image = cv2.imdecode(np.frombuffer(snapshot, np.uint8), cv2.IMREAD_COLOR)
    assert image is not None and image.shape[:2] == (480, 640)
    assert s.sink.calls[1][0]["uid"] == create["uid"]


def test_wearing_a_helmet_makes_no_event():
    s = Scene()
    s.run(4, [(A, RED, True)])
    assert s.sink.calls == []


def test_same_person_returning_after_two_minutes_is_one_event():
    s = Scene()
    s.run(3, [(A, RED, False)])
    s.run(4.5, [])  # leaves; the event ends; the tracker forgets the old id
    s.jump(120)
    s.run(3, [(B, RED, False)])  # comes back elsewhere with a new track id and the same clothes
    s.run(2, [])
    assert s.kinds == ["create", "end", "reopen", "end"]
    uids = {p["uid"] for p in s.sink.payloads}
    assert len(uids) == 1
    reopen = s.sink.payloads[2]
    assert reopen["ended_at"] is None and reopen["occurrences"] == 2
    assert reopen["extra"]["merged_similarity"] > 0.75 and len(reopen["extra"]["track_ids"]) == 2


def test_different_clothes_are_a_different_person():
    s = Scene()
    s.run(3, [(A, RED, False)])
    s.run(4.5, [])
    s.jump(120)
    s.run(3, [(B, BLUE, False)])
    s.run(2, [])
    assert s.kinds.count("create") == 2 and len({p["uid"] for p in s.sink.payloads}) == 2


def test_after_the_merge_window_it_is_a_new_event():
    s = Scene()
    s.run(3, [(A, RED, False)])
    s.run(4.5, [])
    s.jump(11 * 60)
    s.run(3, [(B, RED, False)])
    assert s.kinds.count("create") == 2


def test_two_people_at_the_same_time_are_two_events_even_in_identical_clothes():
    s = Scene()
    s.run(3, [(A, RED, False), (B, RED, False)])
    assert s.kinds == ["create", "create"]
    assert len({p["uid"] for p in s.sink.payloads}) == 2


def test_close_all_ends_open_events_when_the_engine_stops():
    s = Scene()
    s.run(3, [(A, RED, False)])
    s.pipeline.close_all(at(s.clock))
    assert s.kinds == ["create", "end"]


def test_status_for_the_heartbeat():
    s = Scene()
    s.run(2, [(A, RED, False)])
    status = s.pipeline.status()
    assert status["cameras"][0]["id"] == 1 and status["cameras"][0]["open_events"] == 1
    assert status["cameras"][0]["latency_ms"] > 0
