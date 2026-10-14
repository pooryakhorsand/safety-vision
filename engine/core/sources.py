"""
Video sources: a file, an RTSP stream or a webcam.

Every source runs in its own thread and keeps ONLY THE LATEST frame.
If the engine is slower than the camera, old frames are dropped, never queued
(a queue would make the live view lag further and further behind).

    source = open_source("rtsp://...", reconnect_seconds=5)
    source.start()
    ok, frame, timestamp = source.read(timeout=1.0)   # ok=False: no NEW frame yet
    source.stop()

For offline processing use iter_video(): it yields EVERY frame, nothing is dropped.
"""

from __future__ import annotations

import logging
import threading
import time
from abc import ABC, abstractmethod
from collections.abc import Iterator
from datetime import datetime, timedelta
from pathlib import Path

import cv2

log = logging.getLogger(__name__)


def now_utc() -> datetime:
    return datetime.now().astimezone()


class FrameSource(ABC):
    """Common part: thread, latest-frame slot, online flag, measured input FPS."""

    def __init__(self, name: str):
        self.name = name
        self._cond = threading.Condition()
        self._frame = None
        self._timestamp: datetime | None = None
        self._seq = 0  # counts published frames
        self._seen_seq = 0  # last frame handed out by read()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._online = False
        self._finished = False
        self._fps = 0.0
        self._last_publish = 0.0

    # ---- control
    def start(self) -> "FrameSource":
        if self._thread is None:
            self._thread = threading.Thread(target=self._guarded_run, name=f"source-{self.name}", daemon=True)
            self._thread.start()
        return self

    def stop(self) -> None:
        self._stop.set()
        with self._cond:
            self._cond.notify_all()
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None

    # ---- reading
    def read(self, timeout: float = 1.0):
        """Return (True, frame, timestamp) for a NEW frame, else (False, None, None) after `timeout`."""
        with self._cond:
            self._cond.wait_for(lambda: self._seq != self._seen_seq or self._stop.is_set() or self._finished, timeout)
            if self._seq == self._seen_seq:
                return False, None, None
            self._seen_seq = self._seq
            return True, self._frame, self._timestamp

    @property
    def is_online(self) -> bool:
        return self._online

    @property
    def finished(self) -> bool:
        """True when a file (not looping) has been read to the end and all frames were taken."""
        with self._cond:
            return self._finished and self._seq == self._seen_seq

    @property
    def fps_in(self) -> float:
        return self._fps

    # ---- for subclasses
    def _publish(self, frame, timestamp: datetime) -> None:
        now = time.monotonic()
        if self._last_publish:
            gap = now - self._last_publish
            if gap > 0:
                instant = 1.0 / gap
                self._fps = instant if self._fps == 0 else 0.9 * self._fps + 0.1 * instant
        self._last_publish = now
        with self._cond:
            self._frame, self._timestamp = frame, timestamp
            self._seq += 1
            self._cond.notify_all()

    def _guarded_run(self) -> None:
        try:
            self._run()
        except Exception:  # a crashing source must not kill the engine
            log.exception("source %s crashed", self.name)
        finally:
            self._online = False

    @abstractmethod
    def _run(self) -> None: ...


class LiveSource(FrameSource):
    """RTSP stream or webcam. Reconnects by itself when the connection drops."""

    def __init__(self, name: str, target, reconnect_seconds: float = 5.0):
        super().__init__(name)
        self.target = target  # url (str) or webcam index (int)
        self.reconnect_seconds = reconnect_seconds

    def _run(self) -> None:
        capture = None
        while not self._stop.is_set():
            if capture is None:
                capture = cv2.VideoCapture(self.target)
                if not capture.isOpened():
                    capture.release()
                    capture = None
                    self._online = False
                    log.warning(
                        "source %s: cannot open %s, retrying in %.0fs", self.name, self.target, self.reconnect_seconds
                    )
                    self._stop.wait(self.reconnect_seconds)
                    continue
                log.info("source %s: connected", self.name)
            ok, frame = capture.read()
            if not ok:
                log.warning("source %s: lost the stream", self.name)
                capture.release()
                capture = None
                self._online = False
                self._stop.wait(self.reconnect_seconds)
                continue
            self._online = True
            self._publish(frame, now_utc())
        if capture is not None:
            capture.release()


class FileSource(FrameSource):
    """
    A video file played like a camera: frames come out at the file's own speed.
    Timestamps are VIDEO time (start_time + frame index / fps), so results are repeatable.
    """

    def __init__(
        self, name: str, path: str | Path, loop: bool = False, start_time: datetime | None = None, realtime: bool = True
    ):
        super().__init__(name)
        self.path = str(path)
        self.loop = loop
        self.start_time = start_time
        self.realtime = realtime

    def _run(self) -> None:
        start_time = self.start_time or now_utc()
        index = 0  # keeps counting across loops
        wall_start = time.monotonic()
        while not self._stop.is_set():
            capture = cv2.VideoCapture(self.path)
            if not capture.isOpened():
                log.error("source %s: cannot open file %s", self.name, self.path)
                self._finish()
                return
            fps = capture.get(cv2.CAP_PROP_FPS) or 25.0
            self._online = True
            while not self._stop.is_set():
                ok, frame = capture.read()
                if not ok:
                    break
                if self.realtime:
                    delay = wall_start + index / fps - time.monotonic()
                    if delay > 0:
                        self._stop.wait(delay)
                self._publish(frame, start_time + timedelta(seconds=index / fps))
                index += 1
            capture.release()
            if not self.loop:
                self._finish()
                return

    def _finish(self) -> None:
        self._online = False
        with self._cond:
            self._finished = True
            self._cond.notify_all()


def open_source(
    name: str, target, *, loop: bool = False, reconnect_seconds: float = 5.0, start_time: datetime | None = None
) -> FrameSource:
    """
    Pick the right source from the camera's `source_url`:
        "0", "1"           webcam index
        rtsp:// http://    live stream
        anything else      a video file path
    """
    text = str(target).strip()
    if text.isdigit():
        return LiveSource(name, int(text), reconnect_seconds)
    if text.lower().startswith(("rtsp://", "rtmp://", "http://", "https://", "udp://", "tcp://")):
        return LiveSource(name, text, reconnect_seconds)
    return FileSource(name, text, loop=loop, start_time=start_time)


def iter_video(path: str | Path, start_time: datetime | None = None) -> Iterator[tuple[int, object, datetime, float]]:
    """Offline reading: yields (index, frame, video_time, fps) for EVERY frame, no threads, no drops."""
    capture = cv2.VideoCapture(str(path))
    if not capture.isOpened():
        raise FileNotFoundError(f"cannot open video: {path}")
    fps = capture.get(cv2.CAP_PROP_FPS) or 25.0
    start_time = start_time or now_utc()
    try:
        index = 0
        while True:
            ok, frame = capture.read()
            if not ok:
                break
            yield index, frame, start_time + timedelta(seconds=index / fps), fps
            index += 1
    finally:
        capture.release()
