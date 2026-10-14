"""
Engine settings: reads engine.yaml into typed dataclasses.

Rules
  - every number the engine uses comes from here, nothing is hard-coded elsewhere
  - unknown or invalid keys stop the engine at start with a message that names the key
  - the API token is never in the file: the file names an environment variable
"""

from __future__ import annotations

import dataclasses
import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, get_type_hints

import yaml

# Folder that contains engine/ and web/.
PROJECT_ROOT = Path(__file__).resolve().parents[2]


def data_root() -> Path:
    """
    Relative paths in the settings are relative to this folder.
    Installed app: APP_DATA_DIR (config, models, queue and logs live there).
    Development: the project folder.
    """
    value = os.environ.get("APP_DATA_DIR")
    return Path(value).resolve() if value else PROJECT_ROOT


def default_config_path() -> Path:
    if os.environ.get("APP_DATA_DIR"):
        return data_root() / "config" / "engine.yaml"
    return PROJECT_ROOT / "engine" / "config" / "engine.yaml"


class ConfigError(ValueError):
    """Raised when engine.yaml is missing a key or has a bad value."""


def resolve_path(value: str | Path) -> Path:
    """Relative paths are relative to data_root(), so the working folder does not matter."""
    path = Path(value)
    return path if path.is_absolute() else data_root() / path


# ---------------------------------------------------------------- sections
@dataclass
class WebConfig:
    base_url: str = "http://127.0.0.1:8000"
    token_env: str = "ENGINE_API_TOKEN"
    timeout_seconds: float = 5.0
    heartbeat_seconds: float = 5.0
    cameras_refresh_seconds: float = 30.0  # how often the camera list is re-read from the web app
    queue_dir: str = "data/engine_queue"
    token: str = field(default="", metadata={"from_yaml": False})  # filled from the environment


@dataclass
class DeviceConfig:
    gpu: Any = 0  # GPU index or "cpu"
    half: bool = False


@dataclass
class DetectorConfig:
    weights: str
    backend: str = "ultralytics"  # ultralytics | onnx | tensorrt
    classes: list = field(default_factory=list)  # empty = all classes
    imgsz: int = 640
    conf: float = 0.25
    iou: float = 0.7
    agnostic_nms: bool = False


@dataclass
class DetectorsConfig:
    person: DetectorConfig
    equipment: DetectorConfig


@dataclass
class TrackerConfig:
    type: str = "botsort"  # botsort | iou
    reid_weights: str = ""
    with_reid: bool = True
    track_buffer: int = 30
    box_smooth: float = 0.6


@dataclass
class ReidConfig:
    backend: str = "boxmot"  # boxmot (OSNet) | histogram (no model, weak: tests and fallback)
    weights: str = ""
    sample_every_frames: int = 3  # while a person violates, keep one crop every N frames
    min_crop_height: int = 96
    crops_per_track: int = 4
    merge_threshold: float = 0.75
    max_templates: int = 8
    neighbor_cameras: dict = field(default_factory=dict)  # camera id -> list of camera ids


@dataclass
class EventsConfig:
    confirm_seconds: float = 3.0
    clear_seconds: float = 5.0
    pending_grace_seconds: float = 1.0  # a violation may disappear this long without restarting the confirm timer
    merge_window_minutes: float = 10.0
    snapshot_quality: int = 85
    snapshot_max_side: int = 1280


@dataclass
class PpeConfig:
    # Body zone of each item as a fraction of the person's box height (top = 0, feet = 1).
    # The key is matched as a substring of the model's class name.
    zones: dict = field(
        default_factory=lambda: {
            "helmet": [0.00, 0.35],
            "hat": [0.00, 0.35],
            "vest": [0.15, 0.70],
            "shoe": [0.75, 1.00],
            "boot": [0.75, 1.00],
        }
    )
    # Which event is raised when the item is missing. Models differ between customers: edit here.
    items: dict = field(
        default_factory=lambda: {
            "helmet": "no_helmet",
            "hat": "no_helmet",
            "vest": "no_vest",
            "shoe": "no_safety_shoes",
            "boot": "no_safety_shoes",
        }
    )
    # A class name starting with one of these means "item missing" (e.g. "no_helmet").
    missing_prefixes: list = field(default_factory=lambda: ["no_", "no-", "no "])
    zone_margin: float = 0.15
    min_contain: float = 0.5
    vote_window: int = 15
    min_votes: int = 4
    # Colours are BGR: [has the item, does not have it].
    item_colors: dict = field(
        default_factory=lambda: {
            "helmet": [[255, 150, 40], [70, 70, 255]],  # blue   / red
            "hat": [[255, 150, 40], [70, 70, 255]],
            "vest": [[90, 220, 90], [0, 220, 255]],  # green  / yellow
            "shoe": [[220, 90, 170], [0, 140, 255]],  # purple / orange
            "boot": [[220, 90, 170], [0, 140, 255]],
        }
    )


@dataclass
class ModulesConfig:
    ppe: PpeConfig = field(default_factory=PpeConfig)


@dataclass
class RenderConfig:
    max_long_side: int = 1280
    crf: int = 20
    stream_host: str = "127.0.0.1"  # "0.0.0.0" shares the live view with the network (no login!)
    stream_port: int = 8765
    stream_fps: float = 10.0
    stream_max_side: int = 960
    stream_jpeg_quality: int = 80


@dataclass
class SourcesConfig:
    reconnect_seconds: float = 5.0
    loop_files: bool = False


@dataclass
class EngineConfig:
    detectors: DetectorsConfig
    web: WebConfig = field(default_factory=WebConfig)
    device: DeviceConfig = field(default_factory=DeviceConfig)
    tracker: TrackerConfig = field(default_factory=TrackerConfig)
    reid: ReidConfig = field(default_factory=ReidConfig)
    events: EventsConfig = field(default_factory=EventsConfig)
    modules: ModulesConfig = field(default_factory=ModulesConfig)
    render: RenderConfig = field(default_factory=RenderConfig)
    sources: SourcesConfig = field(default_factory=SourcesConfig)


# ---------------------------------------------------------------- building
def _build(cls: type, data: Any, path: str) -> Any:
    """Create dataclass `cls` from a dict, checking names and types. `path` is used in messages."""
    if not isinstance(data, Mapping):
        raise ConfigError(f"'{path or 'engine.yaml'}' must be a section (a mapping), got {type(data).__name__}")

    hints = get_type_hints(cls)
    known = {f.name: f for f in dataclasses.fields(cls) if f.metadata.get("from_yaml", True)}
    for key in data:
        if key not in known:
            raise ConfigError(f"unknown key '{_join(path, key)}'. Allowed here: {', '.join(sorted(known))}")

    values = {}
    for name, f in known.items():
        has_default = f.default is not dataclasses.MISSING or f.default_factory is not dataclasses.MISSING
        if name not in data:
            if not has_default:
                raise ConfigError(f"'{_join(path, name)}' is required")
            continue
        values[name] = _coerce(data[name], hints[name], _join(path, name))
    return cls(**values)


def _coerce(value: Any, hint: Any, path: str) -> Any:
    if dataclasses.is_dataclass(hint):
        return _build(hint, value, path)
    if hint is Any:
        return value
    if hint is bool:
        if not isinstance(value, bool):
            raise ConfigError(f"'{path}' must be true or false, got {value!r}")
        return value
    if hint is int:
        if isinstance(value, bool) or not isinstance(value, int):
            raise ConfigError(f"'{path}' must be a whole number, got {value!r}")
        return value
    if hint is float:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ConfigError(f"'{path}' must be a number, got {value!r}")
        return float(value)
    if hint is str:
        if not isinstance(value, str):
            raise ConfigError(f"'{path}' must be text, got {value!r}")
        return value
    if hint is dict:
        if not isinstance(value, dict):
            raise ConfigError(f"'{path}' must be a mapping, got {value!r}")
        return value
    if hint is list:
        if not isinstance(value, list):
            raise ConfigError(f"'{path}' must be a list, got {value!r}")
        return value
    return value


def _join(path: str, key: str) -> str:
    return f"{path}.{key}" if path else key


# ---------------------------------------------------------------- checks
def _validate(cfg: EngineConfig) -> None:
    def check(ok: bool, key: str, rule: str) -> None:
        if not ok:
            raise ConfigError(f"'{key}' {rule}")

    backends = ("ultralytics", "onnx", "tensorrt")
    for name in ("person", "equipment"):
        det = getattr(cfg.detectors, name)
        check(det.backend in backends, f"detectors.{name}.backend", f"must be one of {backends}")
        check(det.imgsz > 0, f"detectors.{name}.imgsz", "must be greater than 0")
        check(0 <= det.conf <= 1, f"detectors.{name}.conf", "must be between 0 and 1")
        check(0 <= det.iou <= 1, f"detectors.{name}.iou", "must be between 0 and 1")
    check(cfg.tracker.type in ("botsort", "iou"), "tracker.type", "must be 'botsort' or 'iou'")
    check(0 < cfg.tracker.box_smooth <= 1, "tracker.box_smooth", "must be in (0, 1]")
    check(0 <= cfg.reid.merge_threshold <= 1, "reid.merge_threshold", "must be between 0 and 1")
    check(cfg.reid.backend in ("boxmot", "histogram"), "reid.backend", "must be 'boxmot' or 'histogram'")
    check(cfg.reid.sample_every_frames >= 1, "reid.sample_every_frames", "must be at least 1")
    check(cfg.reid.crops_per_track >= 1, "reid.crops_per_track", "must be at least 1")
    check(cfg.reid.max_templates >= 1, "reid.max_templates", "must be at least 1")
    check(cfg.events.confirm_seconds >= 0, "events.confirm_seconds", "must not be negative")
    check(cfg.events.clear_seconds >= 0, "events.clear_seconds", "must not be negative")
    check(cfg.events.pending_grace_seconds >= 0, "events.pending_grace_seconds", "must not be negative")
    check(cfg.events.merge_window_minutes >= 0, "events.merge_window_minutes", "must not be negative")
    check(1 <= cfg.events.snapshot_quality <= 100, "events.snapshot_quality", "must be 1..100")
    ppe = cfg.modules.ppe
    check(ppe.vote_window >= 1, "modules.ppe.vote_window", "must be at least 1")
    check(1 <= ppe.min_votes <= ppe.vote_window, "modules.ppe.min_votes", "must be between 1 and vote_window")
    check(0 <= ppe.min_contain <= 1, "modules.ppe.min_contain", "must be between 0 and 1")
    for item, zone in ppe.zones.items():
        check(
            isinstance(zone, (list, tuple)) and len(zone) == 2 and 0 <= zone[0] <= zone[1] <= 1,
            f"modules.ppe.zones.{item}",
            "must be [top, bottom] with 0 <= top <= bottom <= 1",
        )
    check(cfg.render.max_long_side >= 64, "render.max_long_side", "must be at least 64")
    check(cfg.web.timeout_seconds > 0, "web.timeout_seconds", "must be greater than 0")
    check(cfg.web.heartbeat_seconds > 0, "web.heartbeat_seconds", "must be greater than 0")


# ---------------------------------------------------------------- public
def parse_config(data: Mapping, env: Mapping[str, str] | None = None) -> EngineConfig:
    """Build and validate a config from an already loaded dict (used by tests)."""
    env = os.environ if env is None else env
    cfg = _build(EngineConfig, data or {}, "")
    _apply_launcher_overrides(cfg, env)
    _validate(cfg)
    cfg.web.token = env.get(cfg.web.token_env, "")
    return cfg


def _apply_launcher_overrides(cfg: EngineConfig, env: Mapping[str, str]) -> None:
    """
    The desktop launcher picks free ports at start and passes them as environment variables,
    so engine.yaml does not have to change when a port is busy.
    """
    if env.get("ENGINE_WEB_BASE_URL"):
        cfg.web.base_url = env["ENGINE_WEB_BASE_URL"]
    if env.get("ENGINE_STREAM_PORT"):
        try:
            cfg.render.stream_port = int(env["ENGINE_STREAM_PORT"])
        except ValueError:
            raise ConfigError("ENGINE_STREAM_PORT must be a whole number") from None


def load_config(path: str | Path | None = None, env: Mapping[str, str] | None = None) -> EngineConfig:
    """Read engine.yaml (default: config/engine.yaml in the data folder, or engine/config/engine.yaml in development)."""
    path = Path(path) if path else default_config_path()
    if not path.exists():
        raise ConfigError(
            f"settings file not found: {path}\n"
            f"Copy engine/config/engine.example.yaml to engine/config/engine.yaml and edit it."
        )
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as error:
        raise ConfigError(f"{path.name} is not valid YAML: {error}") from error
    return parse_config(data, env)
