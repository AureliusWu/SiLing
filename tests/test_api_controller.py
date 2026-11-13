import threading
import time

import pytest
from fastapi.testclient import TestClient
from siling_voice.api import create_app
from siling_voice.config import Settings
from siling_voice.controller import Controller


@pytest.fixture
def client(tmp_path):
    controller = Controller(Settings(), tmp_path, demo=True)
    with TestClient(create_app(controller, "test-session-token")) as client:
        yield client, controller


AUTH = {"Authorization": "Bearer test-session-token"}


def wait_for(predicate, timeout=5):
    until = time.monotonic() + timeout
    while time.monotonic() < until:
        if predicate():
            return
        time.sleep(0.02)
    pytest.fail("timed out waiting for worker")


def test_health_is_public_but_audio_controls_require_token(client):
    http, _ = client
    assert http.get("/health").json()["service"] == "SiLing"
    assert http.get("/api/status").status_code == 401
    assert http.post("/api/control", json={"action": "start"}).status_code == 401
    assert http.get("/api/devices", headers=AUTH).status_code == 200
    assert http.get("/api/status", headers=AUTH).json()["state"] == "MUTED"


def test_foreign_origin_and_host_have_no_control(client):
    http, _ = client
    r = http.options(
        "/api/control",
        headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "POST"},
    )
    assert "access-control-allow-origin" not in r.headers
    assert http.get("/health", headers={"host": "evil.example"}).status_code == 400


def test_demo_is_labeled_and_transcribes_without_hardware(client):
    http, controller = client
    http.post("/api/control", json={"action": "start"}, headers=AUTH)
    wait_for(lambda: controller.state == "IDLE")
    http.post("/api/control", json={"action": "wake"}, headers=AUTH)
    wait_for(lambda: any(e["type"] == "transcript" for e in controller.snapshot()["events"]))
    result = http.get("/api/status", headers=AUTH).json()
    assert result["mode"] == "demo"
    assert result["hardware_acceptance"] == "NOT_VERIFIED"
    assert result["cloud"] is False
    assert http.post("/api/control", json={"action": "mute"}, headers=AUTH).status_code == 200
    assert controller.snapshot()["events"] == []
    assert controller.state == "MUTED"


def test_cancel_and_unknown_controls(client):
    http, _ = client
    assert http.post("/api/control", json={"action": "cancel"}, headers=AUTH).status_code == 409
    assert http.post("/api/control", json={"action": "shell"}, headers=AUTH).status_code == 400


def test_invalid_settings_are_rejected_before_mutation(client):
    http, controller = client
    payload = controller.settings.model_dump()
    payload["wake_word"] = "powershell;"
    assert http.put("/api/settings", json=payload, headers=AUTH).status_code == 422
    assert controller.settings.wake_word == "你好司聆"


def test_mute_during_native_load_prevents_late_device_acquisition(tmp_path, monkeypatch):
    loaded, release = threading.Event(), threading.Event()

    def slow_backend(*args):
        loaded.set()
        release.wait(3)
        from siling_voice.backends import DemoBackend

        return DemoBackend()

    monkeypatch.setattr("siling_voice.controller.SherpaBackend", slow_backend)
    controller = Controller(Settings(), tmp_path)
    controller.start()
    assert loaded.wait(2)
    controller.mute()
    release.set()
    controller.thread.join(2)
    assert controller.mic is None
    assert controller.state == "MUTED"
    assert not controller.thread.is_alive()


def test_initialization_failure_can_be_retried(client, monkeypatch):
    _, controller = client
    controller.demo = False
    monkeypatch.setattr(
        "siling_voice.controller.SherpaBackend", lambda *a: (_ for _ in ()).throw(ValueError())
    )
    controller.start()
    wait_for(lambda: controller.state == "ERROR")
    controller.thread.join(2)
    controller.demo = True
    controller.start()
    wait_for(lambda: controller.state == "IDLE")


def test_events_are_bounded_and_cursor_works(client):
    _, controller = client
    for i in range(300):
        controller.emit({"type": "metric", "value": i})
    assert len(controller.snapshot()["events"]) == 128
    assert len(controller.snapshot(after=298)["events"]) == 2
