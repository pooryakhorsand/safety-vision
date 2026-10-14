"""GPU engine: all video processing. Talks to the web app only through web_client/."""

from pathlib import Path

# One version for the whole product: the VERSION file in the project root.
_version_file = Path(__file__).resolve().parent.parent / "VERSION"
__version__ = _version_file.read_text(encoding="utf-8").strip() if _version_file.is_file() else "0.0.0"
