"""
Engine entry point.

    python -m engine.core.main run                       live: cameras come from the web app
    python -m engine.core.main offline --video V.mp4 --camera-id 1 --out results/cam1
    python -m engine.core.main replay --camera 1=results/cam1 --camera 2=results/cam2

Run from the project root (the folder that contains engine/ and web/).
"""

from __future__ import annotations

import argparse
import logging
import os
import signal
import sys
import threading
from datetime import datetime
from pathlib import Path

from engine.core.config import PROJECT_ROOT, ConfigError, EngineConfig, load_config
from engine.core.models_check import describe, missing_models


def build_components(config: EngineConfig):
    """Real detectors, tracker factory and ReID embedder."""
    from engine.perception.detector import build_detector
    from engine.perception.reid import build_embedder
    from engine.perception.tracker import build_tracker

    detectors = {
        "person": build_detector("person", config.detectors.person, config.device),
        "equipment": build_detector("equipment", config.detectors.equipment, config.device),
    }
    embedder = build_embedder(config.reid, config.device)
    return detectors, (lambda: build_tracker(config.tracker, config.device)), embedder


def wait_for_models(config: EngineConfig, missing: list[dict]) -> int:
    """Models are missing: say so clearly and keep reporting it, so the web app can show the reason."""
    from engine import __version__
    from engine.web_client.client import WebClient

    print(describe(missing), file=sys.stderr)
    client = WebClient(config.web).start()
    stop = _stop_on_ctrl_c()
    try:
        while not stop.is_set():
            client.send_heartbeat(
                {
                    "engine_version": __version__,
                    "models_ok": False,
                    "missing_models": missing,
                    "cameras": [],
                }
            )
            stop.wait(config.web.heartbeat_seconds)
    finally:
        client.stop()
    return 2


def command_run(config: EngineConfig, args) -> int:
    from engine.core.pipeline import Pipeline
    from engine.core.runner import LiveRunner
    from engine.render.overlay import FrameRenderer
    from engine.render.stream import StreamServer
    from engine.web_client.client import WebClient

    missing = missing_models(config)
    if missing:
        return wait_for_models(config, missing)

    detectors, tracker_factory, embedder = build_components(config)
    client = WebClient(config.web).start()
    pipeline = Pipeline(config, detectors, client, tracker_factory=tracker_factory, embedder=embedder)

    stream = StreamServer(config.render).start()
    renderer = FrameRenderer(config)

    def on_frame(runtime, result):
        if stream.wants_frame(runtime.camera_id):
            stream.publish(runtime.camera_id, renderer.render(result.ctx))

    runner = LiveRunner(config, client, pipeline, on_frame=on_frame)
    stop = _stop_on_ctrl_c()
    logging.getLogger(__name__).info("engine running. Press Ctrl+C to stop.")
    try:
        runner.run(stop)
    finally:
        stream.stop()
        client.stop()
    return 0


def command_offline(config: EngineConfig, args) -> int:
    from engine.core.offline import run_offline
    from engine.core.pipeline import Pipeline

    missing = missing_models(config)
    if missing:
        print(describe(missing), file=sys.stderr)
        return 2

    detectors, tracker_factory, embedder = build_components(config)
    camera = {"id": args.camera_id, "name": args.name or f"CAM-{args.camera_id:02d}", "modules": args.modules or []}
    start_time = datetime.fromisoformat(args.start_time).astimezone() if args.start_time else None

    def pipeline_factory(sink):
        return Pipeline(config, detectors, sink, tracker_factory=tracker_factory, embedder=embedder)

    summary = run_offline(
        config, pipeline_factory, Path(args.video), Path(args.out), camera=camera, start_time=start_time
    )
    print(
        f"done: {summary.frames} frames ({summary.seconds:.0f} s of video), {summary.events} event lines -> {args.out}"
    )
    return 0


def command_replay(config: EngineConfig, args) -> int:
    import time

    from engine import __version__
    from engine.core.replay import ReplayCamera
    from engine.core.runner import gpu_status
    from engine.render.stream import StreamServer
    from engine.web_client.client import WebClient

    client = WebClient(config.web).start()
    stream = StreamServer(config.render).start()
    stop = _stop_on_ctrl_c()

    cameras = []
    for item in args.camera:
        camera_id, _, directory = item.partition("=")
        if not camera_id.isdigit() or not directory:
            raise SystemExit(f"--camera must look like 1=results/cam1, got '{item}'")
        cameras.append(
            ReplayCamera(
                int(camera_id), Path(directory), client, on_frame=lambda cid, frame: stream.publish(cid, frame)
            )
        )

    threads = [
        threading.Thread(target=camera.run, args=(stop,), name=f"replay-{camera.camera_id}", daemon=True)
        for camera in cameras
    ]
    for thread in threads:
        thread.start()
    started = time.monotonic()
    logging.getLogger(__name__).info("replaying %d camera(s). Press Ctrl+C to stop.", len(cameras))
    try:
        while not stop.wait(config.web.heartbeat_seconds):
            client.send_heartbeat(
                {
                    "engine_version": __version__,
                    "uptime_seconds": round(time.monotonic() - started),
                    "gpu": gpu_status(config),
                    "cameras": [camera.status() for camera in cameras],
                }
            )
    finally:
        stop.set()
        client.flush(5.0)
        client.stop()
        stream.stop()
    return 0


def watch_stdin(stop: threading.Event, stream=None) -> threading.Thread:
    """
    The desktop launcher asks the engine to finish by closing the engine's standard input
    (a way that works on Windows without a console). When it closes, `stop` is set.
    """
    stream = stream if stream is not None else sys.stdin

    def wait_for_close() -> None:
        try:
            while stream.readline():
                pass
        except (OSError, ValueError):
            pass
        stop.set()

    thread = threading.Thread(target=wait_for_close, name="stdin-watch", daemon=True)
    thread.start()
    return thread


def _stop_on_ctrl_c() -> threading.Event:
    stop = threading.Event()
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, lambda *_: stop.set())
    if os.environ.get("ENGINE_STOP_ON_STDIN_CLOSE") == "1":
        watch_stdin(stop)
    return stop


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m engine.core.main", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--config", help="path to engine.yaml (default: engine/config/engine.yaml)")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("run", help="live: cameras come from the web app")

    offline = sub.add_parser("offline", help="process a video file as fast as possible")
    offline.add_argument("--video", required=True)
    offline.add_argument("--camera-id", type=int, required=True)
    offline.add_argument("--out", required=True, help="output folder")
    offline.add_argument("--name", help="camera name (default CAM-01 style)")
    offline.add_argument("--modules", nargs="*", help="modules to run (default: all)")
    offline.add_argument("--start-time", help="ISO time of video second 0 (default: now)")

    replay = sub.add_parser("replay", help="play offline results like live cameras")
    replay.add_argument(
        "--camera",
        action="append",
        required=True,
        metavar="ID=FOLDER",
        help="repeat for each camera, e.g. --camera 1=results/cam1",
    )
    return parser


def setup_logging() -> Path:
    """Console plus a rotating file (10 MB x 5): <data folder>/logs/engine.log."""
    from logging.handlers import RotatingFileHandler

    log_dir = (Path(os.environ["APP_DATA_DIR"]) if os.environ.get("APP_DATA_DIR") else PROJECT_ROOT / "data") / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    handlers = [
        logging.StreamHandler(),
        RotatingFileHandler(log_dir / "engine.log", maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8"),
    ]
    logging.basicConfig(
        level=logging.INFO, handlers=handlers, force=True, format="%(asctime)s %(levelname)-7s %(name)s: %(message)s"
    )
    return log_dir / "engine.log"


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    setup_logging()
    try:
        config = load_config(args.config)
    except ConfigError as error:
        print(f"Settings error: {error}", file=sys.stderr)
        return 2
    return {"run": command_run, "offline": command_offline, "replay": command_replay}[args.command](config, args)


if __name__ == "__main__":
    sys.exit(main())
