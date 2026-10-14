"""
Download the GENERAL models the engine needs. Your own PPE model is never downloaded: you train it
(see docs/models.md).

    python -m engine.tools.download_models              # person detector + appearance model
    python -m engine.tools.download_models --person yolo11m.pt

Files are saved where engine.yaml expects them (the paths of `detectors.person.weights` and
`tracker.reid_weights`). Existing files are kept.
"""

from __future__ import annotations

import argparse
import logging
import shutil
import sys
from pathlib import Path

from engine.core.config import ConfigError, load_config, resolve_path

log = logging.getLogger("download_models")
DEFAULT_PERSON = "yolo11x.pt"
DEFAULT_REID = "osnet_x0_25_msmt17.pt"


def download_person(name: str, target: Path) -> None:
    """Ultralytics downloads a model by its official name into the current folder; move it to `target`."""
    from ultralytics import YOLO

    target.parent.mkdir(parents=True, exist_ok=True)
    cached = Path(name).name
    YOLO(cached)  # downloads when missing
    found = Path(cached)
    if not found.exists():
        raise RuntimeError(f"Ultralytics did not leave {cached} in the current folder")
    shutil.move(str(found), target)


def download_reid(target: Path) -> None:
    """BoxMOT downloads its appearance models when they are missing."""
    from boxmot.appearance.reid.auto_backend import ReidAutoBackend

    target.parent.mkdir(parents=True, exist_ok=True)
    ReidAutoBackend(weights=target, device="cpu", half=False)
    if not target.exists():
        raise RuntimeError(f"BoxMOT did not create {target}")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", help="engine.yaml (default: the usual place)")
    parser.add_argument(
        "--person", default=DEFAULT_PERSON, help=f"official Ultralytics model name (default {DEFAULT_PERSON})"
    )
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    try:
        config = load_config(args.config)
    except (ConfigError, FileNotFoundError) as exc:
        log.error("Cannot read engine.yaml: %s", exc)
        return 1

    jobs = []
    person = Path(config.detectors.person.weights)
    if len(person.parts) > 1:  # a bare name is downloaded by Ultralytics on first use
        jobs.append(("person detector", resolve_path(person), lambda t: download_person(args.person, t)))
    reid = Path(config.tracker.reid_weights) if config.tracker.reid_weights else None
    if reid and len(reid.parts) > 1:
        jobs.append(("appearance model", resolve_path(reid), download_reid))

    failed = 0
    for label, target, run in jobs:
        if target.exists():
            log.info("%s: already there (%s)", label, target)
            continue
        log.info("%s: downloading to %s", label, target)
        try:
            run(target)
        except Exception as exc:  # network, missing package, changed upstream API
            failed += 1
            log.error("%s failed: %s", label, exc)
    if not jobs:
        log.info("Nothing to download: the configured models are downloaded automatically on first use.")
    if failed:
        log.error("Download the failed model(s) by hand and put them at the paths shown above.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
