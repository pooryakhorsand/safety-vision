# Engine

Runs as its own process in its own environment, separate from the web app.
It does all video processing and sends only results (events, snapshots, heartbeat, live pictures)
to the web app through the API in [`docs/engine_api.md`](../docs/engine_api.md).

| Folder | Purpose |
|--------|---------|
| `config/` | `engine.yaml`: models, thresholds, paths |
| `core/` | sources, per-camera pipeline, entry point |
| `perception/` | shared tools: detectors, tracker, ReID |
| `identity/` | recent-violators gallery that merges repeat violations of one person |
| `events/` | event state machine and snapshots (shared by every module) |
| `render/` | overlay drawing, video writer, live stream (display only) |
| `web_client/` | the only code that talks to the web app |
| `modules/` | analysis modules (currently `ppe/`) |
| `tools/` | model export, parity check, benchmark |
| `tests/` | tests that run without a GPU |

Architecture and how to add a module: [`docs/architecture.md`](../docs/architecture.md).
