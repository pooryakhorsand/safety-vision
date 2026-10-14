"""Starting, watching and stopping the two programs (web server, engine)."""

from __future__ import annotations

import logging
import os
import subprocess
import threading
import time
import urllib.request
from collections.abc import Callable
from pathlib import Path

log = logging.getLogger("launcher")

CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0


class RestartPolicy:
    """At most `max_restarts` restarts inside `window_seconds`; after that the program is left stopped."""

    def __init__(
        self, max_restarts: int = 3, window_seconds: float = 300.0, clock: Callable[[], float] = time.monotonic
    ):
        self.max_restarts = max_restarts
        self.window_seconds = window_seconds
        self.clock = clock
        self._times: list[float] = []

    def allow(self) -> bool:
        now = self.clock()
        self._times = [t for t in self._times if now - t < self.window_seconds]
        if len(self._times) >= self.max_restarts:
            return False
        self._times.append(now)
        return True


class ManagedProcess:
    """One child program with its own log file. `stdin_stop` asks the child to finish by closing its stdin."""

    def __init__(
        self,
        name: str,
        command: list[str],
        cwd: Path,
        env: dict[str, str],
        log_path: Path,
        stdin_stop: bool = False,
        grace_seconds: float = 20.0,
        popen: Callable = subprocess.Popen,
    ):
        self.name = name
        self.command = command
        self.cwd = cwd
        self.env = env
        self.log_path = log_path
        self.stdin_stop = stdin_stop
        self.grace_seconds = grace_seconds
        self._popen = popen
        self._process = None
        self._log_file = None

    def start(self) -> None:
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self._log_file = open(self.log_path, "ab")  # noqa: SIM115 (kept open for the child's lifetime)
        env = {**self.env, "ENGINE_STOP_ON_STDIN_CLOSE": "1"} if self.stdin_stop else dict(self.env)
        self._process = self._popen(
            self.command,
            cwd=str(self.cwd),
            env=env,
            stdin=subprocess.PIPE if self.stdin_stop else subprocess.DEVNULL,
            stdout=self._log_file,
            stderr=subprocess.STDOUT,
            creationflags=CREATE_NO_WINDOW,
        )
        log.info("%s started (pid %s)", self.name, getattr(self._process, "pid", "?"))

    def is_running(self) -> bool:
        return self._process is not None and self._process.poll() is None

    def stop(self) -> None:
        process = self._process
        if process is None:
            return
        if process.poll() is None and self.stdin_stop and process.stdin:
            try:
                process.stdin.close()  # the engine sees this, closes its events and flushes its queue
                process.wait(timeout=self.grace_seconds)
            except (subprocess.TimeoutExpired, OSError):
                pass
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
        log.info("%s stopped", self.name)
        if self._log_file:
            self._log_file.close()
            self._log_file = None
        self._process = None


class Supervisor(threading.Thread):
    """Restarts a child that exits by itself, within the restart policy."""

    def __init__(
        self, process: ManagedProcess, policy: RestartPolicy, on_failed: Callable[[str], None], interval: float = 1.0
    ):
        super().__init__(name=f"supervise-{process.name}", daemon=True)
        self.process = process
        self.policy = policy
        self.on_failed = on_failed
        self.interval = interval
        self._stop_event = threading.Event()
        self.failed = False

    def check_once(self) -> None:
        if self.failed or self.process.is_running():
            return
        if self.policy.allow():
            log.warning("%s exited by itself; restarting", self.process.name)
            self.process.start()
        else:
            self.failed = True
            log.error("%s keeps stopping; not restarting any more", self.process.name)
            self.on_failed(self.process.name)

    def run(self) -> None:
        while not self._stop_event.wait(self.interval):
            self.check_once()

    def halt(self) -> None:
        self._stop_event.set()


def wait_until_ready(
    url: str,
    timeout: float = 90.0,
    interval: float = 0.5,
    fetch: Callable[[str], int] | None = None,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> bool:
    """Poll `url` until it answers with a page (any status below 500)."""

    def default_fetch(address: str) -> int:
        try:
            with urllib.request.urlopen(address, timeout=3) as response:
                return response.status
        except urllib.error.HTTPError as error:
            return error.code
        except OSError:
            return 599

    fetch = fetch or default_fetch
    deadline = clock() + timeout
    while clock() < deadline:
        if fetch(url) < 500:
            return True
        sleep(interval)
    return False
