"""
Live view for the browser: MJPEG over HTTP, served by the engine on its own port.

    <img src="http://engine-host:8765/stream/1">

The web app never touches video; the page just points an <img> at this URL.
Only the latest picture of each camera is kept (a slow viewer skips frames instead of lagging behind).
"""

from __future__ import annotations

import logging
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import cv2

from engine.core.config import RenderConfig

log = logging.getLogger(__name__)
BOUNDARY = "engineframe"


class StreamServer:
    def __init__(self, config: RenderConfig):
        self.config = config
        self._frames: dict[int, tuple[int, bytes]] = {}  # camera id -> (frame number, jpeg)
        self._cond = threading.Condition()
        self._server: ThreadingHTTPServer | None = None
        self._last_publish: dict[int, float] = {}

    # ---- called by the pipeline / replay
    def wants_frame(self, camera_id: int) -> bool:
        """Rate limit: the live view needs `stream_fps`, not every processed frame."""
        return time.monotonic() - self._last_publish.get(camera_id, 0.0) >= 1.0 / self.config.stream_fps

    def publish(self, camera_id: int, image) -> None:
        self._last_publish[camera_id] = time.monotonic()
        height, width = image.shape[:2]
        scale = min(1.0, self.config.stream_max_side / max(width, height))
        if scale < 1.0:
            image = cv2.resize(image, (int(width * scale), int(height * scale)), interpolation=cv2.INTER_AREA)
        ok, jpeg = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, self.config.stream_jpeg_quality])
        if not ok:
            return
        with self._cond:
            number = self._frames.get(camera_id, (0, b""))[0] + 1
            self._frames[camera_id] = (number, jpeg.tobytes())
            self._cond.notify_all()

    # ---- server
    def start(self) -> "StreamServer":
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802 (http.server naming)
                parts = self.path.strip("/").split("/")
                if len(parts) == 2 and parts[0] == "stream" and parts[1].isdigit():
                    outer._serve_stream(self, int(parts[1]))
                else:
                    self.send_error(404)

            def log_message(self, *args):  # keep the console quiet
                pass

        self._server = ThreadingHTTPServer((self.config.stream_host, self.config.stream_port), Handler)
        self._server.daemon_threads = True
        threading.Thread(target=self._server.serve_forever, name="stream-server", daemon=True).start()
        log.info("live view on port %s", self._server.server_address[1])
        return self

    @property
    def port(self) -> int:
        return self._server.server_address[1] if self._server else self.config.stream_port

    def stop(self) -> None:
        if self._server:
            self._server.shutdown()
            self._server.server_close()
            self._server = None

    def _serve_stream(self, handler: BaseHTTPRequestHandler, camera_id: int) -> None:
        handler.send_response(200)
        handler.send_header("Content-Type", f"multipart/x-mixed-replace; boundary={BOUNDARY}")
        handler.send_header("Cache-Control", "no-cache, private")
        handler.end_headers()
        last = 0
        try:
            while True:
                with self._cond:
                    self._cond.wait_for(lambda seen=last: self._frames.get(camera_id, (0, b""))[0] != seen, timeout=2.0)
                    number, jpeg = self._frames.get(camera_id, (0, b""))
                if number == last:
                    continue  # nothing new yet; keep waiting
                last = number
                handler.wfile.write(
                    f"--{BOUNDARY}\r\nContent-Type: image/jpeg\r\nContent-Length: {len(jpeg)}\r\n\r\n".encode()
                    + jpeg
                    + b"\r\n"
                )
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass  # the viewer closed the tab
