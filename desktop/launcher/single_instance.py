"""Only one launcher per computer: a second start asks the first one to show its window and exits."""

from __future__ import annotations

import socket
import threading
import zlib
from collections.abc import Callable


def port_for(name: str) -> int:
    """A stable local port in 47000-47999 derived from the product's short name."""
    return 47000 + zlib.crc32(name.encode("utf-8")) % 1000


class SingleInstance:
    def __init__(self, port: int, on_focus: Callable[[], None] | None = None):
        self.port = port
        self.on_focus = on_focus
        self._server: socket.socket | None = None

    def acquire(self) -> bool:
        """True: this is the first launcher. False: another one runs (it was asked to show its window)."""
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            server.bind(("127.0.0.1", self.port))
        except OSError:
            server.close()
            self._ask_first_instance()
            return False
        server.listen(5)
        self._server = server
        threading.Thread(target=self._listen, name="single-instance", daemon=True).start()
        return True

    def _ask_first_instance(self) -> None:
        try:
            with socket.create_connection(("127.0.0.1", self.port), timeout=2) as connection:
                connection.sendall(b"focus")
        except OSError:
            pass

    def _listen(self) -> None:
        while self._server is not None:
            try:
                connection, _ = self._server.accept()
            except OSError:
                return
            with connection:
                connection.settimeout(1)
                try:
                    message = connection.recv(16)
                except OSError:
                    message = b""
            if message == b"focus" and self.on_focus:
                self.on_focus()

    def release(self) -> None:
        server, self._server = self._server, None
        if server:
            server.close()
