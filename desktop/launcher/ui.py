"""The parts the person sees: the window around the console, the tray icon and error boxes."""

from __future__ import annotations

import logging
import os
import webbrowser
from collections.abc import Callable
from pathlib import Path

log = logging.getLogger("launcher")


def show_error(title: str, text: str) -> None:
    """A message box on Windows, otherwise the log. The launcher has no console of its own."""
    log.error("%s: %s", title, text)
    if os.name == "nt":
        import ctypes

        ctypes.windll.user32.MessageBoxW(None, text, title, 0x10)


def open_folder(path: Path) -> None:
    if os.name == "nt":
        os.startfile(str(path))  # noqa: S606
    else:
        webbrowser.open(path.as_uri())


class Window:
    """pywebview window; falls back to the default browser when pywebview or WebView2 is missing."""

    def __init__(self, title: str, url: str):
        self.title, self.url = title, url
        self._window = None

    def run(self) -> bool:
        """Show the window and block until it is closed. Returns False when no window could be made."""
        try:
            import webview

            self._window = webview.create_window(self.title, self.url, width=1366, height=820, min_size=(1000, 640))
            webview.start()
            return True
        except Exception as error:  # missing package, no WebView2 runtime, no display
            log.warning("native window not available (%s); using the browser", error)
            webbrowser.open(self.url)
            return False

    def show(self) -> None:
        if self._window is not None:
            try:
                self._window.show()
                self._window.restore()
            except Exception:  # the window may be closing
                pass
        else:
            webbrowser.open(self.url)

    def close(self) -> None:
        if self._window is not None:
            try:
                self._window.destroy()
            except Exception:
                pass


class Tray:
    """Tray icon with Open, Restart engine, Open logs folder, Quit."""

    def __init__(
        self,
        title: str,
        icon_path: Path,
        on_open: Callable,
        on_restart: Callable,
        on_logs: Callable,
        on_quit: Callable,
        labels: dict[str, str] | None = None,
    ):
        self.title, self.icon_path = title, icon_path
        self.handlers = (on_open, on_restart, on_logs, on_quit)
        self.labels = labels or {
            "open": "Open",
            "restart": "Restart engine",
            "logs": "Open logs folder",
            "quit": "Quit",
        }
        self._icon = None

    def start(self) -> bool:
        try:
            import pystray
            from PIL import Image

            on_open, on_restart, on_logs, on_quit = self.handlers
            menu = pystray.Menu(
                pystray.MenuItem(self.labels["open"], lambda *_: on_open(), default=True),
                pystray.MenuItem(self.labels["restart"], lambda *_: on_restart()),
                pystray.MenuItem(self.labels["logs"], lambda *_: on_logs()),
                pystray.MenuItem(self.labels["quit"], lambda *_: on_quit()),
            )
            self._icon = pystray.Icon(self.title, Image.open(self.icon_path), self.title, menu)
            self._icon.run_detached()
            return True
        except Exception as error:
            log.warning("tray icon not available (%s)", error)
            return False

    def notify(self, message: str) -> None:
        if self._icon is not None:
            try:
                self._icon.notify(message, self.title)
            except Exception:
                pass

    def stop(self) -> None:
        if self._icon is not None:
            try:
                self._icon.stop()
            except Exception:
                pass
