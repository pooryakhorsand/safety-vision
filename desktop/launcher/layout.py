"""Where things are: program files, runtimes and the data folder (installed app or development checkout)."""

from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path

import yaml

WINDOWS = os.name == "nt"


@dataclass(frozen=True)
class Layout:
    app_dir: Path  # folder with VERSION, web/, engine/, profiles/, desktop/
    data_dir: Path  # config, database, media, logs, models, queue
    web_python: Path
    engine_python: Path
    short_name: str
    product_name: str
    version: str
    installed: bool

    @property
    def web_dir(self) -> Path:
        return self.app_dir / "web"

    @property
    def config_dir(self) -> Path:
        return self.data_dir / "config"

    @property
    def logs_dir(self) -> Path:
        return self.data_dir / "logs"

    @property
    def models_dir(self) -> Path:
        return self.data_dir / "models"


def runtime_python(runtime_dir: Path) -> Path:
    return runtime_dir / "python.exe" if WINDOWS else runtime_dir / "bin" / "python"


def read_profile(app_dir: Path, profile_key: str) -> dict:
    path = app_dir / "profiles" / profile_key / "profile.yaml"
    with path.open(encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def detect(env: dict | None = None, app_dir: Path | None = None) -> Layout:
    """
    Installed app:   <install>/app/ + <install>/runtime/web|engine/, data in %ProgramData%/<ShortName>
    Development:     the checkout itself, current Python for both programs, data in <checkout>/data
    Environment overrides: APP_DATA_DIR, APP_WEB_PYTHON, APP_ENGINE_PYTHON, SITE_PROFILE.
    """
    env = dict(os.environ if env is None else env)
    app_dir = (app_dir or Path(__file__).resolve().parents[2]).resolve()
    runtime = app_dir.parent / "runtime"
    installed = runtime.is_dir()

    profile = read_profile(app_dir, env.get("SITE_PROFILE", "default"))
    short_name = str(profile.get("short_name", ""))
    if not re.match(r"^[A-Za-z][A-Za-z0-9]{1,29}$", short_name):
        raise ValueError("profile.yaml: 'short_name' must be 2-30 letters or digits, starting with a letter")
    product_name = (profile.get("product_name") or {}).get("en", short_name)

    if env.get("APP_DATA_DIR"):
        data_dir = Path(env["APP_DATA_DIR"])
    elif installed:
        data_dir = Path(env.get("PROGRAMDATA", r"C:\ProgramData")) / short_name
    else:
        data_dir = app_dir / "data"

    if installed:
        web_python = Path(env.get("APP_WEB_PYTHON") or runtime_python(runtime / "web"))
        engine_python = Path(env.get("APP_ENGINE_PYTHON") or runtime_python(runtime / "engine"))
    else:
        web_python = Path(env.get("APP_WEB_PYTHON") or sys.executable)
        engine_python = Path(env.get("APP_ENGINE_PYTHON") or sys.executable)

    version_file = app_dir / "VERSION"
    version = version_file.read_text(encoding="utf-8").strip() if version_file.is_file() else "0.0.0"
    return Layout(app_dir, data_dir.resolve(), web_python, engine_python, short_name, product_name, version, installed)
