"""Launcher tests. Child programs are replaced by fakes, so nothing real is started."""

import json
import socket
import sys
import threading
from pathlib import Path

import pytest

from desktop.launcher import app, firstrun, layout, ports, single_instance, system_check
from desktop.launcher.supervisor import ManagedProcess, RestartPolicy, Supervisor, wait_until_ready

PROJECT = Path(__file__).resolve().parents[2]


def make_layout(tmp_path) -> layout.Layout:
    return layout.detect(env={"APP_DATA_DIR": str(tmp_path / "data")}, app_dir=PROJECT)


# ------------------------------------------------------------------ layout
def test_layout_reads_names_from_the_profile_and_uses_the_data_override(tmp_path):
    found = make_layout(tmp_path)
    assert found.short_name == "SafetyVision" and found.version == (PROJECT / "VERSION").read_text().strip()
    assert found.data_dir == (tmp_path / "data").resolve() and not found.installed
    assert found.web_python == Path(sys.executable)


def test_installed_layout_uses_program_data_and_the_bundled_runtimes(tmp_path):
    install = tmp_path / "Program Files" / "Safety"
    (install / "runtime" / "web").mkdir(parents=True)
    app_dir = install / "app"
    (app_dir / "profiles" / "default").mkdir(parents=True)
    (app_dir / "profiles" / "default" / "profile.yaml").write_text("short_name: SafetyVision\n")
    found = layout.detect(env={"PROGRAMDATA": str(tmp_path / "ProgramData")}, app_dir=app_dir)
    assert found.installed
    assert found.data_dir == (tmp_path / "ProgramData" / "SafetyVision").resolve()
    assert "runtime" in found.web_python.parts and "web" in found.web_python.parts


def test_bad_short_name_is_refused(tmp_path):
    app_dir = tmp_path / "app"
    (app_dir / "profiles" / "default").mkdir(parents=True)
    (app_dir / "profiles" / "default" / "profile.yaml").write_text("short_name: 'bad name!'\n")
    with pytest.raises(ValueError):
        layout.detect(env={}, app_dir=app_dir)


# ------------------------------------------------------------------- ports
def test_busy_port_is_skipped():
    with socket.socket() as busy:
        busy.bind(("127.0.0.1", 0))
        taken = busy.getsockname()[1]
        chosen = ports.pick_port(taken)
        assert chosen != taken and ports.is_free(chosen)
    assert ports.pick_port(taken, taken=(taken,)) != taken


# ---------------------------------------------------------------- first run
def test_first_run_creates_secrets_and_engine_settings_once(tmp_path):
    found = make_layout(tmp_path)
    assert sorted(firstrun.ensure_config(found)) == [".env", "engine.yaml"]
    for folder in firstrun.DATA_FOLDERS:
        assert (found.data_dir / folder).is_dir()

    values = firstrun.read_env_file(found.config_dir / ".env")
    assert len(values["DJANGO_SECRET_KEY"]) >= 32 and len(values["ENGINE_API_TOKEN"]) >= 32
    assert values["DJANGO_DEBUG"] == "False"
    assert "models/ppe.pt" in (found.config_dir / "engine.yaml").read_text()

    (found.config_dir / "engine.yaml").write_text("edited: true\n")
    assert firstrun.ensure_config(found) == []  # nothing is overwritten
    assert (found.config_dir / "engine.yaml").read_text() == "edited: true\n"
    assert firstrun.read_env_file(found.config_dir / ".env") == values


def test_desktop_engine_settings_are_valid_for_the_engine(tmp_path):
    from engine.core.config import load_config

    found = make_layout(tmp_path)
    firstrun.ensure_config(found)
    config = load_config(found.config_dir / "engine.yaml", env={"ENGINE_API_TOKEN": "t", "ENGINE_STREAM_PORT": "8800"})
    assert config.render.stream_port == 8800 and config.detectors.equipment.weights == "models/ppe.pt"


# ----------------------------------------------------------- single instance
def test_second_launcher_asks_the_first_to_show_itself():
    port = ports.pick_port(47500)
    shown = threading.Event()
    first = single_instance.SingleInstance(port, on_focus=shown.set)
    second = single_instance.SingleInstance(port)
    try:
        assert first.acquire() is True
        assert second.acquire() is False
        assert shown.wait(3)
    finally:
        first.release()
    assert 47000 <= single_instance.port_for("SafetyVision") < 48000


# ------------------------------------------------------------ restart policy
def test_restart_policy_allows_three_restarts_in_five_minutes():
    now = [0.0]
    policy = RestartPolicy(3, 300, clock=lambda: now[0])
    assert [policy.allow() for _ in range(4)] == [True, True, True, False]
    now[0] = 301
    assert policy.allow() is True  # the old restarts have aged out


class FakeProcess:
    def __init__(self):
        self.returncode, self.stdin, self.terminated = None, None, False
        self.pid = 1

    def poll(self):
        return self.returncode

    def terminate(self):
        self.terminated, self.returncode = True, -15

    def kill(self):
        self.returncode = -9

    def wait(self, timeout=None):
        return self.returncode


def test_supervisor_restarts_then_gives_up(tmp_path):
    started, failed = [], []

    def popen(command, **kwargs):
        process = FakeProcess()
        started.append(process)
        return process

    managed = ManagedProcess("engine", ["x"], tmp_path, {}, tmp_path / "log.txt", popen=popen)
    managed.start()
    supervisor = Supervisor(managed, RestartPolicy(3, 300), failed.append)
    for _ in range(6):
        started[-1].returncode = 1  # the child dies every time
        supervisor.check_once()
    assert len(started) == 4  # first start + 3 restarts
    assert failed == ["engine"]
    supervisor.check_once()
    assert failed == ["engine"]  # reported once


def test_stop_closes_stdin_first_so_the_engine_can_finish(tmp_path):
    closed = []

    class Pipe:
        def close(self):
            closed.append(True)

    def popen(command, **kwargs):
        process = FakeProcess()
        process.stdin = Pipe()
        process.wait = lambda timeout=None: setattr(process, "returncode", 0)
        return process

    managed = ManagedProcess("engine", ["x"], tmp_path, {}, tmp_path / "log.txt", stdin_stop=True, popen=popen)
    managed.start()
    process = managed._process
    managed.stop()
    assert closed == [True] and not process.terminated and not managed.is_running()


def test_real_child_stops_when_its_stdin_closes(tmp_path):
    code = "import sys; sys.stdin.read(); print('bye')"
    managed = ManagedProcess(
        "child", [sys.executable, "-c", code], tmp_path, {}, tmp_path / "child.log", stdin_stop=True
    )
    managed.start()
    assert managed.is_running()
    managed.stop()
    assert "bye" in (tmp_path / "child.log").read_text()


# -------------------------------------------------------------------- waiting
def test_wait_until_ready_polls_until_the_page_answers():
    answers = iter([599, 599, 200])
    clock = [0.0]
    ok = wait_until_ready(
        "http://x",
        timeout=10,
        fetch=lambda url: next(answers),
        sleep=lambda s: clock.__setitem__(0, clock[0] + s),
        clock=lambda: clock[0],
    )
    assert ok
    clock[0] = 0
    assert not wait_until_ready(
        "http://x",
        timeout=2,
        fetch=lambda url: 599,
        sleep=lambda s: clock.__setitem__(0, clock[0] + s),
        clock=lambda: clock[0],
    )


# ----------------------------------------------------------- commands and env
def test_commands_and_environment(tmp_path):
    found = make_layout(tmp_path)
    env = app.child_environment(found, {"ENGINE_API_TOKEN": "tok"}, 8001, 8766)
    assert env["APP_DATA_DIR"] == str(found.data_dir) and env["ENGINE_API_TOKEN"] == "tok"
    assert env["ENGINE_WEB_BASE_URL"] == "http://127.0.0.1:8001" and env["ENGINE_STREAM_URL"] == "http://127.0.0.1:8766"
    assert "--listen=127.0.0.1:8001" in app.web_command(found, 8001)
    assert app.engine_command(found)[1:] == ["-m", "engine.core.main", "run"]


def test_maintenance_runs_after_ten_minutes_then_daily():
    now, runs = [0.0], []
    timer = app.MaintenanceTimer(lambda: runs.append(now[0]), clock=lambda: now[0])
    assert timer.tick() is False
    now[0] = 601
    assert timer.tick() is True and timer.tick() is False
    now[0] = 601 + 24 * 3600
    assert timer.tick() is True and len(runs) == 2


# ---------------------------------------------------------------- system check
def test_system_check_file(tmp_path):
    found = make_layout(tmp_path)
    firstrun.ensure_config(found)
    (found.models_dir / "ppe.pt").write_bytes(b"x")

    class Result:
        returncode, stdout = 0, "NVIDIA GeForce GTX 1650, 552.12, 4096\n"

    path = system_check.write_system_check(found, True, run=lambda *a, **k: Result())
    data = json.loads(path.read_text())
    assert data["gpu"] == {"name": "NVIDIA GeForce GTX 1650", "driver": "552.12", "memory_mb": 4096}
    assert data["cuda_available"] is True and data["disk"]["free_gb"] > 0
    by_key = {m["key"]: m["found"] for m in data["models"]}
    assert by_key == {"detectors.person.weights": False, "detectors.equipment.weights": True}


def test_no_gpu_is_reported_as_none():
    def no_tool(*args, **kwargs):
        raise FileNotFoundError

    assert system_check.gpu_info(no_tool) is None
    assert system_check.cuda_available(Path("missing"), no_tool) is None


# ------------------------------------------------------------------- icons
def test_icon_is_made_from_the_profile_logo(tmp_path):
    pytest.importorskip("fitz")
    pytest.importorskip("PIL")
    from PIL import Image

    from desktop.build.make_icon import make_icons

    ico, tray = make_icons(PROJECT / "profiles" / "default" / "assets" / "logo.svg", tmp_path)
    with Image.open(ico) as image:
        assert 256 in {size[0] for size in image.info["sizes"]} and 16 in {size[0] for size in image.info["sizes"]}
    with Image.open(tray) as image:
        assert image.size == (64, 64) and image.getpixel((32, 4))[3] > 0 or image.getpixel((32, 32))[3] > 0
