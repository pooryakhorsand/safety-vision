import json
import threading
import time

import cv2
import numpy as np

from engine.core.offline import run_offline
from engine.core.pipeline import Pipeline
from engine.core.replay import ReplayCamera
from engine.core.runner import LiveRunner
from engine.core.sources import FileSource
from engine.perception.reid import HistogramEmbedder
from engine.perception.tracker import IouTracker
from engine.render.stream import StreamServer
from engine.tests.conftest import CollectingSink, det, make_config
from engine.tests.fakes import ScriptedDetector
from engine.web_client.client import WebClient

PERSON = (100, 50, 220, 400)


def violating_detectors():
    """One person who never wears a helmet, in every frame."""
    return {
        "person": ScriptedDetector(lambda n, img: [det("person", PERSON)]),
        "equipment": ScriptedDetector(lambda n, img: [det("no_helmet", (130, 50, 190, 90))]),
    }


def write_big_video(path, frames=40, fps=10):
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"MJPG"), fps, (640, 480))
    for i in range(frames):
        image = np.full((480, 640, 3), 40, np.uint8)
        image[50:400, 100:220] = (60 + i, 120, 200)
        writer.write(image)
    writer.release()


def test_offline_makes_video_events_and_snapshots(tmp_path):
    video, out = tmp_path / "in.avi", tmp_path / "out"
    write_big_video(video)
    config = make_config()

    def factory(sink):
        return Pipeline(
            config,
            violating_detectors(),
            sink,
            tracker_factory=lambda: IouTracker(config.tracker),
            embedder=HistogramEmbedder(),
        )

    summary = run_offline(config, factory, video, out, camera={"id": 1, "name": "CAM-01", "modules": ["ppe"]})
    assert summary.frames == 40 and summary.events == 2

    rendered = cv2.VideoCapture(str(out / "rendered.mp4"))
    assert rendered.isOpened() and int(rendered.get(cv2.CAP_PROP_FRAME_COUNT)) == 40
    lines = [json.loads(line) for line in (out / "events.jsonl").read_text().splitlines()]
    assert [line["kind"] for line in lines] == ["create", "end"]
    assert 1.0 <= lines[0]["send_t"] <= 2.0 and lines[0]["t"] < lines[0]["send_t"]  # starts before it is confirmed
    assert (out / lines[0]["snapshot"]).exists()


def test_replay_sends_the_recorded_events_with_new_uids_and_current_times(tmp_path):
    video, out = tmp_path / "in.avi", tmp_path / "out"
    write_big_video(video)
    config = make_config()
    run_offline(
        config,
        lambda sink: Pipeline(config, violating_detectors(), sink, tracker_factory=lambda: IouTracker(config.tracker)),
        video,
        out,
        camera={"id": 1, "name": "CAM-01", "modules": ["ppe"]},
    )
    recorded = [json.loads(line) for line in (out / "events.jsonl").read_text().splitlines()]

    sink, frames = CollectingSink(), []
    replay = ReplayCamera(7, out, sink, loop=False, speed=50, on_frame=lambda cid, frame: frames.append(cid))
    replay.run(threading.Event())

    assert len(frames) > 30 and set(frames) == {7}
    assert [("event_type" in p) for p in sink.payloads] == [True, False]
    create, end = sink.payloads
    assert create["uid"] == end["uid"] != recorded[0]["payload"]["uid"]
    assert create["camera_id"] == 7  # the replay camera, not the recorded one
    assert sink.calls[0][1][:2] == b"\xff\xd8"  # the snapshot travels along
    assert create["started_at"] < end["ended_at"]

    again = CollectingSink()
    ReplayCamera(7, out, again, loop=False, speed=50).run(threading.Event())
    assert again.payloads[0]["uid"] != create["uid"]  # a new pass is a new event


def test_live_runner_reads_cameras_from_the_web_sends_events_and_a_heartbeat(web, tmp_path):
    video = tmp_path / "cam.avi"
    write_big_video(video, frames=40, fps=10)
    web.cameras = [{"id": 1, "name": "CAM-01", "source_url": str(video), "modules": ["ppe"]}]
    config = make_config(web={"base_url": web.url, "queue_dir": str(tmp_path / "q"), "heartbeat_seconds": 0.5})

    client = WebClient(config.web, retry_seconds=0.1).start()
    pipeline = Pipeline(
        config,
        violating_detectors(),
        client,
        tracker_factory=lambda: IouTracker(config.tracker),
        embedder=HistogramEmbedder(),
    )
    runner = LiveRunner(config, client, pipeline)
    stop = threading.Event()
    thread = threading.Thread(target=runner.run, args=(stop,), daemon=True)
    thread.start()

    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        runtime = pipeline.runtimes.get(1)
        if runtime is not None and runtime.source.finished:
            break
        time.sleep(0.1)
    stop.set()
    thread.join(timeout=10)
    client.stop()

    paths = [r["path"] for r in web.requests]
    assert "/api/engine/cameras/" in paths and "/api/engine/heartbeat/" in paths
    events = [r for r in web.requests if r["path"] == "/api/events/"]
    assert len(events) == 2 and b"no_helmet" in events[0]["body"] and b"ended_at" in events[1]["body"]
    heartbeat = [json.loads(r["body"]) for r in web.requests if r["path"] == "/api/engine/heartbeat/"][-1]
    assert heartbeat["cameras"][0]["id"] == 1 and heartbeat["engine_version"]


def test_runner_picks_up_added_changed_and_removed_cameras(tmp_path):
    config = make_config()
    sink = CollectingSink()
    pipeline = Pipeline(config, violating_detectors(), sink, tracker_factory=lambda: IouTracker(config.tracker))
    started = []

    def source_factory(name, url, **kw):
        source = FileSource(name, url, realtime=False)
        source.start = lambda: started.append(url) or source
        return source

    runner = LiveRunner(config, sink, pipeline, source_factory=source_factory)
    runner.sync_cameras([{"id": 1, "name": "A", "source_url": "a.mp4", "modules": ["ppe"]}])
    runner.sync_cameras([{"id": 1, "name": "A", "source_url": "a.mp4", "modules": ["ppe"]}])  # unchanged
    assert started == ["a.mp4"]
    runner.sync_cameras(
        [
            {"id": 1, "name": "A", "source_url": "b.mp4", "modules": ["ppe"]},
            {"id": 2, "name": "B", "source_url": "c.mp4", "modules": []},
        ]
    )
    assert started == ["a.mp4", "b.mp4", "c.mp4"] and set(pipeline.runtimes) == {1, 2}
    runner.sync_cameras([])
    assert pipeline.runtimes == {}


def test_live_view_serves_mjpeg(tmp_path):
    import requests

    server = StreamServer(make_config(render={"stream_port": 0}).render).start()
    try:
        server.publish(1, np.full((100, 200, 3), 90, np.uint8))
        response = requests.get(f"http://127.0.0.1:{server.port}/stream/1", stream=True, timeout=5)
        assert "multipart/x-mixed-replace" in response.headers["Content-Type"]
        chunk = next(response.iter_content(chunk_size=64))
        assert b"--engineframe" in chunk and b"image/jpeg" in chunk
        response.close()
        assert requests.get(f"http://127.0.0.1:{server.port}/nope", timeout=5).status_code == 404
    finally:
        server.stop()


def test_missing_models_are_reported_clearly(tmp_path):
    from engine.core.models_check import describe, missing_models

    cfg = make_config()
    cfg.detectors.equipment.weights = str(tmp_path / "ppe.pt")
    cfg.detectors.person.weights = "yolo11x.pt"  # bare name: downloaded by Ultralytics, not checked
    missing = missing_models(cfg)
    assert [m["key"] for m in missing] == ["detectors.equipment.weights"]
    assert "ppe.pt" in describe(missing) and "detectors.equipment.weights" in describe(missing)
    (tmp_path / "ppe.pt").write_bytes(b"x")
    assert missing_models(cfg) == []


def test_stream_listens_on_localhost_by_default():
    assert make_config().render.stream_host == "127.0.0.1"


def test_engine_stops_when_its_stdin_is_closed():
    import io

    from engine.core.main import watch_stdin

    stop = threading.Event()
    watch_stdin(stop, io.StringIO(""))  # closed input: the launcher asked the engine to finish
    assert stop.wait(2)


def test_download_models_fetches_only_missing_general_models(tmp_path, monkeypatch):
    from engine.tools import download_models as tool

    cfg = make_config()
    cfg.detectors.person.weights = str(tmp_path / "models" / "person.pt")
    cfg.tracker.reid_weights = str(tmp_path / "models" / "reid.pt")
    (tmp_path / "models").mkdir()
    (tmp_path / "models" / "reid.pt").write_bytes(b"x")  # already there: must be kept
    calls = []
    monkeypatch.setattr(tool, "load_config", lambda path=None: cfg)
    monkeypatch.setattr(
        tool, "download_person", lambda name, target: calls.append(("person", name)) or target.write_bytes(b"y")
    )
    monkeypatch.setattr(tool, "download_reid", lambda target: calls.append(("reid",)))

    assert tool.main([]) == 0
    assert calls == [("person", "yolo11x.pt")] and (tmp_path / "models" / "person.pt").exists()
