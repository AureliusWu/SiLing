import asyncio
import json
import threading
import time

import httpx
import pytest
from siling_voice.config import Settings
from siling_voice.dialogue import Dialogue
from siling_voice.providers import Cancelled, Provider, ProviderFailure
from siling_voice.secrets import KeyStore


class TestKeys:
    def get(self):
        return "private-test-key"


def done(dialogue):
    dialogue.thread.join(5)
    assert not dialogue.thread.is_alive()


def test_three_real_protocol_turns_context_and_local_speaker_mock(tmp_path):
    requests, events = [], []

    def handler(request):
        requests.append(json.loads(request.content))
        assert request.headers["authorization"] == "Bearer private-test-key"
        return httpx.Response(200, json={"choices": [{"message": {"content": "中文答复。"}}]})

    settings = Settings(
        provider="compatible",
        api_base="https://api.example.test/v1",
        cloud_consent=True,
        tts="mock",
    )
    provider = Provider(settings, TestKeys(), httpx.MockTransport(handler))
    dialogue = Dialogue(settings, tmp_path, events.append, provider=provider)
    for text in ["我叫小明", "我叫什么名字", "请继续"]:
        dialogue.submit(text)
        done(dialogue)
    assert [len(r["messages"]) for r in requests] == [2, 4, 6]
    assert len([e for e in events if e["type"] == "assistant"]) == 3
    assert dialogue.state == "IDLE" and not dialogue.active
    assert len(dialogue.history) == 6
    assert "private-test-key" not in str(events)
    assert not list(tmp_path.glob("*.wav"))


@pytest.mark.parametrize("status", [401, 429, 500, 302])
def test_http_failures_are_redacted_and_recoverable(tmp_path, status):
    settings = Settings(provider="ollama")
    transport = httpx.MockTransport(lambda r: httpx.Response(status, text="private-secret-body"))
    events = []
    dialogue = Dialogue(
        settings, tmp_path, events.append, provider=Provider(settings, transport=transport)
    )
    dialogue.submit("用户隐私文字")
    done(dialogue)
    assert not dialogue.active
    assert f"PROVIDER_HTTP_{status}" in str(events)
    assert "private-secret-body" not in str(events)


def test_cancel_closes_inflight_request_before_reply(tmp_path):
    started = threading.Event()

    async def handler(request):
        started.set()
        await asyncio.sleep(20)
        return httpx.Response(200, json={"choices": [{"message": {"content": "late"}}]})

    provider = Provider(Settings(provider="ollama"), transport=httpx.MockTransport(handler))
    cancel = threading.Event()
    errors = []
    thread = threading.Thread(target=lambda: invoke(errors))

    def invoke(errors):
        try:
            provider.complete([{"role": "user", "content": "hi"}], cancel)
        except Exception as error:
            errors.append(error)

    thread.start()
    assert started.wait(2)
    then = time.monotonic()
    cancel.set()
    thread.join(1)
    assert not thread.is_alive() and time.monotonic() - then < 1
    assert len(errors) == 1 and isinstance(errors[0], Cancelled)


def test_timeout_and_bad_json():
    async def delayed(request):
        await asyncio.sleep(20)
        return httpx.Response(200, json={})

    provider = Provider(
        Settings(provider="ollama", request_timeout_s=2), transport=httpx.MockTransport(delayed)
    )
    with pytest.raises(ProviderFailure, match="PROVIDER_TIMEOUT"):
        provider.complete([], threading.Event())
    provider.transport = httpx.MockTransport(lambda r: httpx.Response(200, text="invalid"))
    with pytest.raises(ProviderFailure, match="PROVIDER_RESPONSE_INVALID"):
        provider.complete([], threading.Event())


def test_speaker_cancel_drops_context_and_does_not_stick(tmp_path):
    playing = threading.Event()

    class Speaker:
        def speak(self, text, cancel):
            playing.set()
            cancel.wait(3)
            raise Cancelled()

        def stop(self):
            pass

    settings = Settings(provider="mock", tts="mock")
    events = []
    dialogue = Dialogue(settings, tmp_path, events.append, speaker=Speaker())
    dialogue.submit("测试")
    assert playing.wait(2)
    dialogue.cancel()
    done(dialogue)
    assert not dialogue.active and not dialogue.history
    assert dialogue.last_metrics["outcome"] == "cancelled"


def test_history_is_opt_in_and_clear_deletes_saved(tmp_path, monkeypatch):
    monkeypatch.setenv("SILING_CONFIG_DIR", str(tmp_path))
    dialogue = Dialogue(Settings(provider="mock"), tmp_path, lambda e: None)
    dialogue.submit("不保存")
    done(dialogue)
    assert not (tmp_path / "history.json").exists()
    dialogue = Dialogue(Settings(provider="mock", save_history=True), tmp_path, lambda e: None)
    dialogue.submit("明确选择保存")
    done(dialogue)
    assert (tmp_path / "history.json").exists()
    dialogue.clear()
    assert not dialogue.history and not (tmp_path / "history.json").exists()


def test_endpoint_and_cloud_consent_validation():
    for url in ["http://public.example/v1", "https://user:secret@host/v1", "file:///etc/passwd"]:
        with pytest.raises(ValueError):
            Settings(api_base=url)
    with pytest.raises(ValueError):
        Settings(provider="compatible", api_base="https://api.example/v1")
    with pytest.raises(ValueError):
        Settings(provider="ollama", api_base="https://public.example/v1")


@pytest.mark.skipif(__import__("sys").platform != "win32", reason="Windows DPAPI")
def test_real_windows_user_dpapi(tmp_path, monkeypatch):
    monkeypatch.delenv("SILING_API_KEY", raising=False)
    keys = KeyStore(tmp_path / "test.dpapi")
    keys.set("only-a-fixture-key")
    assert b"only-a-fixture-key" not in keys.path.read_bytes()
    assert keys.configured() and keys.get() == "only-a-fixture-key"
    keys.delete()
    assert not keys.configured()
