import time

from engine.core.sources import FileSource, LiveSource, iter_video, open_source
from engine.tests.conftest import write_video


def test_file_source_delivers_every_frame_with_video_timestamps(tmp_path):
    video = tmp_path / "a.avi"
    write_video(video, frames=10, fps=10)
    source = FileSource("t", video).start()
    stamps = []
    deadline = time.monotonic() + 10
    while not source.finished and time.monotonic() < deadline:
        ok, frame, ts = source.read(timeout=0.5)
        if ok:
            stamps.append(ts)
    source.stop()
    assert len(stamps) == 10
    assert abs((stamps[-1] - stamps[0]).total_seconds() - 0.9) < 0.01  # video time, not wall time


def test_loop_restarts_and_keeps_time_increasing(tmp_path):
    video = tmp_path / "a.avi"
    write_video(video, frames=5, fps=50)
    source = FileSource("t", video, loop=True).start()
    stamps = []
    deadline = time.monotonic() + 5
    while len(stamps) < 12 and time.monotonic() < deadline:
        ok, _, ts = source.read(timeout=0.5)
        if ok:
            stamps.append(ts)
    source.stop()
    assert len(stamps) >= 12 and stamps == sorted(stamps) and not source.finished


def test_slow_consumer_gets_latest_frame_not_a_queue(tmp_path):
    video = tmp_path / "a.avi"
    write_video(video, frames=20, fps=100)
    source = FileSource("t", video).start()
    time.sleep(0.6)  # file is over before we read anything
    ok, frame, ts = source.read(timeout=0.5)
    ok_again, *_ = source.read(timeout=0.05)
    source.stop()
    assert ok and not ok_again  # exactly one (the latest) frame is waiting
    assert frame.mean() > 180  # the last frame (index 19 * 10), JPEG makes it approximate


def test_bad_stream_reports_offline_and_does_not_crash():
    source = LiveSource("bad", "rtsp://127.0.0.1:1/none", reconnect_seconds=0.2).start()
    ok, frame, ts = source.read(timeout=0.8)
    assert not ok and not source.is_online
    source.stop()


def test_open_source_chooses_the_kind(tmp_path):
    assert isinstance(open_source("a", "0"), LiveSource)
    assert isinstance(open_source("a", "rtsp://host/stream"), LiveSource)
    assert isinstance(open_source("a", str(tmp_path / "x.mp4")), FileSource)


def test_iter_video_yields_every_frame(tmp_path):
    video = tmp_path / "a.avi"
    write_video(video, frames=7, fps=10)
    frames = list(iter_video(video))
    assert [f[0] for f in frames] == list(range(7))
