"""Writes the rendered video as H.264 through ffmpeg (OpenCV's own mp4v writer is much worse)."""

from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path

import cv2

log = logging.getLogger(__name__)


def find_ffmpeg() -> str | None:
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    try:
        import imageio_ffmpeg  # pip install imageio-ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


class VideoWriter:
    def __init__(self, path: str | Path, fps: float, size: tuple[int, int], crf: int = 20):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._process = None
        self._fallback = None
        exe = find_ffmpeg()
        if exe:
            command = [
                exe,
                "-y",
                "-loglevel",
                "error",
                "-f",
                "rawvideo",
                "-pix_fmt",
                "bgr24",
                "-s",
                f"{size[0]}x{size[1]}",
                "-r",
                f"{fps:.3f}",
                "-i",
                "-",
                "-an",
                "-c:v",
                "libx264",
                "-preset",
                "medium",
                "-crf",
                str(crf),
                "-pix_fmt",
                "yuv420p",
                "-movflags",
                "+faststart",
                str(self.path),
            ]
            self._process = subprocess.Popen(command, stdin=subprocess.PIPE)
        else:
            log.warning("ffmpeg not found (pip install imageio-ffmpeg): falling back to mp4v, lower quality")
            self._fallback = cv2.VideoWriter(str(self.path), cv2.VideoWriter_fourcc(*"mp4v"), fps, size)

    def write(self, frame) -> None:
        if self._process:
            self._process.stdin.write(frame.tobytes())
        else:
            self._fallback.write(frame)

    def close(self) -> None:
        if self._process:
            self._process.stdin.close()
            self._process.wait()
            self._process = None
        elif self._fallback:
            self._fallback.release()
            self._fallback = None
