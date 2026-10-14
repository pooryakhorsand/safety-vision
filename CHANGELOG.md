# Changelog

All notable changes are listed here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and the version in the `VERSION` file follows [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Changed
- Overview page is now a management summary for today, 7 days or 30 days: totals with comparison to the previous
  period, critical and not-acknowledged counts, chart over time, breakdown by event type and camera, open alarms,
  and a print button for the period.

## [1.0.0]

### Added
- Operator console (Django): live camera grid with the engine's picture, overview, settings, English and Persian
  interface (right-to-left), white-label profiles, admin and operator roles.
- Events: management channel with filters, paging, CSV export, printable report, acknowledge, live counters,
  retention and daily backup.
- Camera management page: add, edit, enable or disable, delete; live state from the engine.
- People list and "Who is this?" assignment by the operator, with a history of changes.
- Engine: sources (RTSP, files, webcam), person detector and tracker, appearance-based merge of repeat violations,
  event state machine, snapshots, live MJPEG view, offline processing and replay of recordings.
- PPE module: helmet, safety vest, safety shoes.
- Model tools: export to ONNX or TensorRT, parity check, benchmark. ONNX Runtime backend.
- Heartbeat from the engine to the web app, with model-file checks.
- Windows desktop app: launcher, first-run setup, installer.
