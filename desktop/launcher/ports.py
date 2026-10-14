"""Free local ports."""

from __future__ import annotations

import socket

HOST = "127.0.0.1"


def is_free(port: int, host: str = HOST) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        try:
            probe.bind((host, port))
        except OSError:
            return False
    return True


def pick_port(preferred: int, host: str = HOST, tries: int = 50, taken: tuple[int, ...] = ()) -> int:
    """The preferred port if free, otherwise the next free one. `taken` are ports already given out."""
    for port in range(preferred, preferred + tries):
        if port not in taken and is_free(port, host):
            return port
    raise OSError(f"no free port found from {preferred} to {preferred + tries - 1}")
