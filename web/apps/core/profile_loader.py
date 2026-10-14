"""
Customer profile loader.

Reads profiles/<SITE_PROFILE>/profile.yaml once and exposes it as a simple
SiteProfile object. Settings, templates and the module registry all read
the profile from here, so changing a customer never means changing code.

This file must not import Django models: settings.py imports it.
"""

import os
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import yaml

# <project root>/profiles  (this file is web/apps/core/profile_loader.py)
PROFILES_DIR = Path(__file__).resolve().parents[3] / "profiles"

SUPPORTED_LANGUAGES = ("fa", "en")
_HEX_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")
_SHORT_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9]{1,29}$")


class ProfileError(Exception):
    """Raised when a profile file is missing or invalid."""


@dataclass(frozen=True)
class SiteProfile:
    key: str  # folder name, e.g. "default"
    directory: Path  # absolute path of the profile folder
    product_name: dict  # {"en": "...", "fa": "..."}
    short_name: str  # letters and digits only: folder and installer names
    site_name: dict  # {"en": "...", "fa": "..."}
    logo: str  # file name inside assets/
    accent_color: str  # "#rrggbb"
    default_language: str  # "fa" or "en"
    time_zone: str  # IANA name, e.g. "Asia/Tehran"
    retention_days: int = 30  # events and their files older than this are deleted
    enabled_modules: list = field(default_factory=list)
    releases_url: str = ""  # where model files can be downloaded (shown on the system check panel)

    @property
    def assets_dir(self) -> Path:
        return self.directory / "assets"

    def text(self, value: dict, language: str) -> str:
        """Return the value for the given language, falling back to English."""
        return value.get(language) or value.get("en") or ""


def _bilingual(raw: dict, name: str) -> dict:
    value = raw.get(name)
    if isinstance(value, str):
        return {"en": value, "fa": value}
    if not isinstance(value, dict) or not value.get("en"):
        raise ProfileError(f"'{name}' must have at least an 'en' value.")
    return {lang: str(value.get(lang, value["en"])) for lang in SUPPORTED_LANGUAGES}


@lru_cache(maxsize=1)
def get_profile(key: str | None = None) -> SiteProfile:
    """Load and validate the active profile (cached after the first call)."""
    key = key or os.environ.get("SITE_PROFILE", "default")
    directory = PROFILES_DIR / key
    path = directory / "profile.yaml"
    if not path.is_file():
        raise ProfileError(f"Profile file not found: {path}")

    with path.open(encoding="utf-8") as handle:
        raw = yaml.safe_load(handle) or {}

    accent = str(raw.get("accent_color", "#2f81f7"))
    if not _HEX_COLOR.match(accent):
        raise ProfileError("'accent_color' must look like #2f81f7.")

    language = str(raw.get("default_language", "en"))
    if language not in SUPPORTED_LANGUAGES:
        raise ProfileError(f"'default_language' must be one of {SUPPORTED_LANGUAGES}.")

    modules = raw.get("enabled_modules") or []
    if not isinstance(modules, list):
        raise ProfileError("'enabled_modules' must be a list.")

    try:
        retention_days = int(raw.get("retention_days", 30))
    except (TypeError, ValueError):
        raise ProfileError("'retention_days' must be a whole number.") from None
    if retention_days < 1:
        raise ProfileError("'retention_days' must be at least 1.")

    short_name = str(raw.get("short_name", "")).strip()
    if not _SHORT_NAME.match(short_name):
        raise ProfileError("'short_name' must be 2-30 letters or digits and start with a letter, e.g. SafetyVision.")

    return SiteProfile(
        key=key,
        directory=directory,
        product_name=_bilingual(raw, "product_name"),
        short_name=short_name,
        releases_url=str(raw.get("releases_url", "") or "").strip(),
        site_name=_bilingual(raw, "site_name"),
        logo=str(raw.get("logo", "logo.svg")),
        accent_color=accent,
        default_language=language,
        time_zone=str(raw.get("time_zone", "UTC")),
        retention_days=retention_days,
        enabled_modules=[str(m) for m in modules],
    )
