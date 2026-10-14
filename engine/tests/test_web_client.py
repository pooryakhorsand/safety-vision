import time

from engine.tests.conftest import make_config
from engine.web_client.client import WebClient


def client_for(web, tmp_path, **kw):
    cfg = make_config(web={"base_url": web.url, "queue_dir": str(tmp_path / "q"), "timeout_seconds": 2})
    return WebClient(cfg.web, retry_seconds=0.1, max_retry_seconds=0.2, **kw).start()


def test_camera_list_uses_the_token(web, tmp_path):
    client = client_for(web, tmp_path)
    assert client.get_cameras()[0]["name"] == "CAM-01"
    assert web.requests[0]["auth"] == "Bearer test-token"
    client.stop()


def test_event_is_delivered_and_queue_is_emptied(web, tmp_path):
    client = client_for(web, tmp_path)
    client.send_event({"uid": "u1", "event_type": "no_helmet"})
    assert client.flush(5)
    assert web.json_posts() == [{"uid": "u1", "event_type": "no_helmet"}]
    client.stop()


def test_snapshot_goes_as_multipart_with_empty_field_for_none(web, tmp_path):
    client = client_for(web, tmp_path)
    client.send_event({"uid": "u1", "ended_at": None, "extra": {"a": 1}}, snapshot=b"\xff\xd8jpeg")
    assert client.flush(5)
    post = [r for r in web.requests if r["method"] == "POST"][0]
    assert "multipart/form-data" in post["type"]
    assert b'name="ended_at"\r\n\r\n\r\n' in post["body"]
    assert b'{"a": 1}' in post["body"] and b"jpeg" in post["body"]
    client.stop()


def test_server_down_keeps_events_in_order_then_delivers_once(web, tmp_path):
    web.status = 503
    client = client_for(web, tmp_path)
    for name in ("create", "end"):
        client.send_event({"uid": "u1", "step": name})
    time.sleep(0.4)
    assert client.pending() == 2  # nothing lost while the server is failing
    web.status = 200
    assert client.flush(5)
    steps = [p["step"] for p in web.json_posts() if p["step"]]
    assert steps[-2:] == ["create", "end"]  # order kept
    assert steps.count("create") >= 1
    client.stop()


def test_queue_survives_restart(web, tmp_path):
    web.status = 503
    first = client_for(web, tmp_path)
    first.send_event({"uid": "u9"})
    time.sleep(0.3)
    first.stop()
    web.status = 200
    second = client_for(web, tmp_path)
    assert second.flush(5)
    assert any(p.get("uid") == "u9" for p in web.json_posts())
    second.stop()


def test_rejected_event_does_not_block_the_queue(web, tmp_path):
    web.status = 400
    client = client_for(web, tmp_path)
    client.send_event({"uid": "bad"})
    assert client.flush(5)
    assert list((tmp_path / "q" / "rejected").glob("*.json"))
    client.stop()


def test_unreachable_server_never_raises_in_send_event(tmp_path):
    cfg = make_config(web={"base_url": "http://127.0.0.1:1", "queue_dir": str(tmp_path / "q"), "timeout_seconds": 0.5})
    client = WebClient(cfg.web, retry_seconds=0.1).start()
    client.send_event({"uid": "x"})  # returns at once
    assert client.pending() == 1
    assert client.send_heartbeat({"cameras": []}) is False
    client.stop()
