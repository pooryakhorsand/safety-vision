# core/

The per-camera loop and the entry point.

| File | Job |
|------|-----|
| `config.py` | Reads `engine.yaml` into typed settings and validates it |
| `sources.py` | File, RTSP and webcam readers that keep only the latest frame |
| `frame.py` | The data passed between steps (detections, tracks, observations) |
| `pipeline.py` | One frame through detection, tracking, modules, events and snapshots |
| `runner.py` | Live mode: reads the camera list from the web app, sends the heartbeat |
| `offline.py` | Processes a video file into `rendered.mp4`, `events.jsonl` and `snapshots/` |
| `replay.py` | Plays an offline result back as a live camera |
| `models_check.py` | Checks that the model files exist and explains what is missing |
| `main.py` | Command line: `run`, `offline`, `replay` |
