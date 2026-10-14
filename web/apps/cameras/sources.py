"""Rules for camera source addresses: what is accepted, and how a password is hidden on screen."""

import re

URL_PATTERN = re.compile(r"^(rtsps?|https?)://[^\s/]+", re.IGNORECASE)
PASSWORD_PATTERN = re.compile(r"^((?:rtsps?|https?)://[^:/@\s]+):[^@\s]*@", re.IGNORECASE)
WINDOWS_PATH = re.compile(r"^[A-Za-z]:[\\/]")


def is_valid_source(value: str) -> bool:
    """RTSP/HTTP stream URL, a video file path (absolute), or a webcam index like 0."""
    value = value.strip()
    if not value:
        return False
    return bool(
        URL_PATTERN.match(value) or value.isdigit() or WINDOWS_PATH.match(value) or value.startswith(("/", "\\\\"))
    )


def mask_source(value: str) -> str:
    """rtsp://user:secret@host/x -> rtsp://user:***@host/x (the password never reaches the page)."""
    return PASSWORD_PATTERN.sub(r"\1:***@", value or "")
