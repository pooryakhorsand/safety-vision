"""What this computer offers (GPU, CUDA, disk, model files). Written for the web app's System check panel."""

from __future__ import annotations

import json
import shutil
import subprocess
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

import yaml

from desktop.launcher.layout import Layout


def gpu_info(run: Callable = subprocess.run) -> dict | None:
    """Name, driver and memory of the first NVIDIA GPU, or None when there is none."""
    try:
        result = run(
            ["nvidia-smi", "--query-gpu=name,driver_version,memory.total", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            timeout=15,
            creationflags=_no_window(),
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0 or not result.stdout.strip():
        return None
    name, driver, memory = [part.strip() for part in result.stdout.strip().splitlines()[0].split(",")][:3]
    return {"name": name, "driver": driver, "memory_mb": int(float(memory))}


def cuda_available(engine_python: Path, run: Callable = subprocess.run) -> bool | None:
    """Ask the engine's own Python whether PyTorch sees a GPU. None when that cannot be found out."""
    try:
        result = run(
            [str(engine_python), "-c", "import torch; print(torch.cuda.is_available())"],
            capture_output=True,
            text=True,
            timeout=120,
            creationflags=_no_window(),
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip().splitlines()[-1] == "True"


def disk_info(path: Path) -> dict:
    usage = shutil.disk_usage(path)
    return {"free_gb": round(usage.free / 1024**3, 1), "total_gb": round(usage.total / 1024**3, 1)}


def model_files(layout: Layout) -> list[dict]:
    """The detector model files named in engine.yaml and whether they exist."""
    path = layout.config_dir / "engine.yaml"
    try:
        settings = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return []
    found = []
    for name in ("person", "equipment"):
        weights = ((settings.get("detectors") or {}).get(name) or {}).get("weights")
        if weights:
            full = Path(weights) if Path(weights).is_absolute() else layout.data_dir / weights
            found.append({"key": f"detectors.{name}.weights", "path": str(full), "found": full.exists()})
    return found


def write_system_check(
    layout: Layout, cuda: bool | None, engine_failed: bool = False, run: Callable = subprocess.run
) -> Path:
    data = {
        "checked_at": datetime.now().isoformat(timespec="seconds"),
        "gpu": gpu_info(run),
        "cuda_available": cuda,
        "disk": disk_info(layout.data_dir),
        "models": model_files(layout),
        "engine_failed": engine_failed,
    }
    target = layout.config_dir / "system_check.json"
    temp = target.with_suffix(".tmp")
    temp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    temp.replace(target)
    return target


def _no_window() -> int:
    import os

    return 0x08000000 if os.name == "nt" else 0
