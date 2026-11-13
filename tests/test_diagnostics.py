import io
import json
import zipfile

from fastapi.testclient import TestClient
from siling_voice.api import create_app
from siling_voice.config import Settings
from siling_voice.controller import Controller
from siling_voice.diagnostics import diagnostic_zip


def test_diagnostics_omit_every_sensitive_payload(tmp_path, monkeypatch):
    poison = "PRIVATE_KEY_TRANSCRIPT_DEVICE_PATH"
    monkeypatch.setenv("SILING_API_KEY", poison)
    controller = Controller(Settings(wake_word="私人名字"), tmp_path / poison, demo=True)
    controller.emit({"type": "transcript", "text": poison})
    controller.emit({"type": "assistant", "text": poison})
    controller.emit({"type": "error", "code": poison})
    controller.emit({"type": "error", "code": "PROVIDER_TIMEOUT"})
    controller.emit({"type": "metric", "llm_ms": 30, "text": poison, "api_key": poison})
    with zipfile.ZipFile(io.BytesIO(diagnostic_zip(controller))) as archive:
        assert archive.namelist() == ["diagnostics.json"]
        text = archive.read("diagnostics.json").decode()
        assert poison not in text and "私人名字" not in text and str(tmp_path) not in text
        data = json.loads(text)
        assert data["error_codes"] == ["PROVIDER_TIMEOUT"] and data["metrics"] == [{"llm_ms": 30}]


def test_export_requires_authorization_and_never_persists_audio(tmp_path):
    controller = Controller(Settings(), tmp_path, demo=True)
    with TestClient(create_app(controller, "safe-token")) as http:
        assert http.get("/api/diagnostics/download").status_code == 401
        response = http.get(
            "/api/diagnostics/download", headers={"Authorization": "Bearer safe-token"}
        )
        assert response.status_code == 200 and response.headers["content-type"] == "application/zip"
    assert not list(tmp_path.glob("*.wav"))
