"""
The desktop app: starts the web server and the engine, shows the console in a window, keeps both running.

Order at start: one-instance lock -> data folder and secrets -> migrate -> web server -> window/tray -> engine.
Order at quit:  engine first (it closes open events and sends what is queued), then the web server.
"""

from __future__ import annotations

import logging
import os
import subprocess
import threading
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path

from desktop.launcher import firstrun, ports, single_instance, system_check, ui
from desktop.launcher import layout as layout_module
from desktop.launcher.supervisor import ManagedProcess, RestartPolicy, Supervisor, wait_until_ready

log = logging.getLogger("launcher")

WEB_PORT, STREAM_PORT = 8000, 8765
MAINTENANCE_FIRST_AFTER = 10 * 60
MAINTENANCE_EVERY = 24 * 3600


def setup_logging(logs_dir: Path) -> None:
    logs_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        force=True,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        handlers=[
            RotatingFileHandler(logs_dir / "launcher.log", maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8")
        ],
    )


def child_environment(layout, secrets: dict[str, str], web_port: int, stream_port: int) -> dict[str, str]:
    """The environment shared by both programs. Secrets come from config/.env."""
    env = {k: v for k, v in os.environ.items() if k not in ("PYTHONHOME", "PYTHONPATH")}
    env.update(secrets)
    env.update(
        {
            "APP_DATA_DIR": str(layout.data_dir),
            "PYTHONPATH": str(layout.app_dir),
            "PYTHONUNBUFFERED": "1",
            "PYTHONUTF8": "1",
            "ENGINE_WEB_BASE_URL": f"http://127.0.0.1:{web_port}",
            "ENGINE_STREAM_PORT": str(stream_port),
            "ENGINE_STREAM_URL": f"http://127.0.0.1:{stream_port}",
        }
    )
    return env


def web_command(layout, web_port: int) -> list[str]:
    return [
        str(layout.web_python),
        "-m",
        "waitress",
        f"--listen=127.0.0.1:{web_port}",
        "--threads=8",
        "web_config.wsgi:application",
    ]


def engine_command(layout) -> list[str]:
    return [str(layout.engine_python), "-m", "engine.core.main", "run"]


def run_manage(layout, env: dict[str, str], *args: str, timeout: float = 600) -> subprocess.CompletedProcess:
    return subprocess.run(
        [str(layout.web_python), "manage.py", *args],
        cwd=str(layout.web_dir),
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout,
        creationflags=0x08000000 if os.name == "nt" else 0,
    )


def ensure_translations(layout, env: dict[str, str]) -> None:
    """The compiled Persian texts (.mo) ship with the app; rebuild them if the file is missing."""
    if (layout.web_dir / "locale" / "fa" / "LC_MESSAGES" / "django.mo").exists():
        return
    script = layout.app_dir / "scripts" / "compile_translations.py"
    if script.exists():
        subprocess.run([str(layout.web_python), str(script)], cwd=str(layout.app_dir), env=env, capture_output=True)


class MaintenanceTimer:
    """Runs the daily clean-up and backup: 10 minutes after start, then every 24 hours."""

    def __init__(self, run, clock=time.monotonic):
        self.run, self.clock = run, clock
        self.next_at = clock() + MAINTENANCE_FIRST_AFTER

    def tick(self) -> bool:
        if self.clock() < self.next_at:
            return False
        self.next_at = self.clock() + MAINTENANCE_EVERY
        self.run()
        return True


class LauncherApp:
    def __init__(self, layout):
        self.layout = layout
        self.stop_event = threading.Event()
        self.window: ui.Window | None = None
        self.tray: ui.Tray | None = None
        self.web: ManagedProcess | None = None
        self.engine: ManagedProcess | None = None
        self.engine_supervisor: Supervisor | None = None
        self.engine_failed = False
        self.cuda: bool | None = None

    # ---------------------------------------------------------------- start
    def run(self) -> int:
        layout = self.layout
        lock = single_instance.SingleInstance(single_instance.port_for(layout.short_name), on_focus=self.show_window)
        if not lock.acquire():
            return 0
        try:
            firstrun.ensure_config(layout)
            setup_logging(layout.logs_dir)
            log.info("%s %s starting (data folder %s)", layout.product_name, layout.version, layout.data_dir)

            secrets = firstrun.read_env_file(layout.config_dir / ".env")
            web_port = ports.pick_port(WEB_PORT)
            stream_port = ports.pick_port(STREAM_PORT, taken=(web_port,))
            env = child_environment(layout, secrets, web_port, stream_port)

            ensure_translations(layout, env)
            migrated = run_manage(layout, env, "migrate", "--noinput")
            if migrated.returncode != 0:
                ui.show_error(layout.product_name, f"The database could not be prepared.\n\n{migrated.stderr[-1500:]}")
                return 1

            self.web = ManagedProcess(
                "web",
                web_command(layout, web_port),
                layout.web_dir,
                env,
                layout.logs_dir / "web-server.log",
                grace_seconds=0,
            )
            self.web.start()
            if not wait_until_ready(f"http://127.0.0.1:{web_port}/accounts/login/"):
                ui.show_error(layout.product_name, f"The console did not start. See the log in {layout.logs_dir}.")
                return 1

            self.start_engine(env)
            threading.Thread(target=self.check_system, name="system-check", daemon=True).start()
            threading.Thread(target=self.maintenance_loop, args=(env,), name="maintenance", daemon=True).start()

            url = f"http://127.0.0.1:{web_port}/"
            self.window = ui.Window(layout.product_name, url)
            self.tray = ui.Tray(
                layout.product_name,
                layout.app_dir / "desktop" / "assets" / "tray.png",
                on_open=self.show_window,
                on_restart=self.restart_engine,
                on_logs=lambda: ui.open_folder(layout.logs_dir),
                on_quit=self.quit,
            )
            self.tray.start()
            if not self.window.run():
                self.stop_event.wait()  # no native window: stay alive until "Quit" in the tray
            return 0
        finally:
            self.shutdown()
            lock.release()

    # ------------------------------------------------------------- engine
    def start_engine(self, env: dict[str, str]) -> None:
        layout = self.layout
        self.engine_env = env
        self.engine = ManagedProcess(
            "engine",
            engine_command(layout),
            layout.app_dir,
            env,
            layout.logs_dir / "engine-output.log",
            stdin_stop=True,
        )
        self.engine.start()
        self.engine_supervisor = Supervisor(self.engine, RestartPolicy(3, 300), self.on_engine_failed)
        self.engine_supervisor.start()

    def on_engine_failed(self, name: str) -> None:
        self.engine_failed = True
        system_check.write_system_check(self.layout, self.cuda, engine_failed=True)
        ui.show_error(
            self.layout.product_name,
            "The engine stopped several times and was not restarted.\n"
            f"Open the tray icon and choose Open logs folder ({self.layout.logs_dir}).",
        )

    def restart_engine(self) -> None:
        if self.engine is None:
            return
        log.info("engine restart requested")
        if self.engine_supervisor:
            self.engine_supervisor.halt()
        self.engine.stop()
        self.engine_failed = False
        self.start_engine(self.engine_env)
        threading.Thread(target=self.check_system, name="system-check", daemon=True).start()

    # ------------------------------------------------------------ helpers
    def check_system(self) -> None:
        if self.cuda is None:
            self.cuda = system_check.cuda_available(self.layout.engine_python)
        system_check.write_system_check(self.layout, self.cuda, self.engine_failed)

    def maintenance_loop(self, env: dict[str, str]) -> None:
        timer = MaintenanceTimer(lambda: run_manage(self.layout, env, "run_maintenance"))
        while not self.stop_event.wait(60):
            try:
                timer.tick()
            except Exception:
                log.exception("maintenance failed")

    def show_window(self) -> None:
        if self.window:
            self.window.show()

    def quit(self) -> None:
        self.stop_event.set()
        if self.window:
            self.window.close()

    def shutdown(self) -> None:
        self.stop_event.set()
        if self.tray:
            self.tray.stop()
        if self.engine_supervisor:
            self.engine_supervisor.halt()
        if self.engine:
            self.engine.stop()
        if self.web:
            self.web.stop()


def main() -> int:
    layout = layout_module.detect()
    return LauncherApp(layout).run()
