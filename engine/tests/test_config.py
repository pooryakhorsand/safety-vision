import pytest

from engine.core.config import ConfigError, load_config, parse_config
from engine.tests.conftest import BASE, make_config


def test_example_file_loads(tmp_path):
    from engine.core.config import PROJECT_ROOT

    cfg = load_config(PROJECT_ROOT / "engine/config/engine.example.yaml", env={"ENGINE_API_TOKEN": "abc"})
    assert cfg.detectors.person.classes == [0]
    assert cfg.web.token == "abc"


def test_defaults_are_applied():
    cfg = make_config()
    assert cfg.events.snapshot_quality == 85
    assert cfg.modules.ppe.items["helmet"] == "no_helmet"
    assert cfg.sources.reconnect_seconds == 5.0


def test_token_comes_from_the_named_environment_variable():
    data = {**BASE, "web": {"token_env": "MY_TOKEN"}}
    assert parse_config(data, env={"MY_TOKEN": "secret"}).web.token == "secret"
    assert parse_config(data, env={}).web.token == ""


def test_missing_required_key_names_the_key():
    with pytest.raises(ConfigError, match=r"detectors\.person\.weights"):
        parse_config({"detectors": {"person": {}, "equipment": {"weights": "x"}}}, env={})
    with pytest.raises(ConfigError, match="detectors"):
        parse_config({}, env={})


def test_unknown_key_is_refused():
    with pytest.raises(ConfigError, match=r"events\.confirm_second"):
        parse_config({**BASE, "events": {"confirm_second": 3}}, env={})


def test_wrong_type_and_range_are_refused():
    with pytest.raises(ConfigError, match=r"events\.confirm_seconds"):
        parse_config({**BASE, "events": {"confirm_seconds": "three"}}, env={})
    with pytest.raises(ConfigError, match=r"reid\.merge_threshold"):
        parse_config({**BASE, "reid": {"merge_threshold": 1.5}}, env={})
    with pytest.raises(ConfigError, match=r"tracker\.type"):
        parse_config({**BASE, "tracker": {"type": "nope"}}, env={})


def test_token_cannot_be_put_in_the_file():
    with pytest.raises(ConfigError, match="web.token"):
        parse_config({**BASE, "web": {"token": "leak"}}, env={})


def test_missing_file_explains_what_to_do(tmp_path):
    with pytest.raises(ConfigError, match="engine.example.yaml"):
        load_config(tmp_path / "nope.yaml")


def test_relative_paths_follow_the_data_folder(tmp_path, monkeypatch):
    from engine.core.config import PROJECT_ROOT, default_config_path, resolve_path

    monkeypatch.delenv("APP_DATA_DIR", raising=False)
    assert resolve_path("models/ppe.pt") == PROJECT_ROOT / "models/ppe.pt"
    assert default_config_path() == PROJECT_ROOT / "engine/config/engine.yaml"

    monkeypatch.setenv("APP_DATA_DIR", str(tmp_path))
    assert resolve_path("models/ppe.pt") == tmp_path.resolve() / "models/ppe.pt"
    assert default_config_path() == tmp_path.resolve() / "config" / "engine.yaml"
    assert resolve_path(str(tmp_path / "x.pt")) == tmp_path / "x.pt"  # absolute paths stay as they are


def test_engine_log_goes_to_the_data_folder(tmp_path, monkeypatch):
    import logging

    from engine.core.main import setup_logging

    monkeypatch.setenv("APP_DATA_DIR", str(tmp_path))
    try:
        path = setup_logging()
        logging.getLogger("x").info("hello")
        assert path == tmp_path / "logs" / "engine.log" and path.exists()
    finally:
        for handler in list(logging.getLogger().handlers):
            handler.close()
            logging.getLogger().removeHandler(handler)


def test_launcher_can_override_web_address_and_stream_port():
    from engine.core.config import PROJECT_ROOT

    cfg = load_config(
        PROJECT_ROOT / "engine/config/engine.example.yaml",
        env={"ENGINE_API_TOKEN": "t", "ENGINE_WEB_BASE_URL": "http://127.0.0.1:8123", "ENGINE_STREAM_PORT": "8800"},
    )
    assert cfg.web.base_url == "http://127.0.0.1:8123" and cfg.render.stream_port == 8800
    assert cfg.web.token == "t"
