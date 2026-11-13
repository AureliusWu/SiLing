import json
import os
import wave
from pathlib import Path

import numpy as np
import pytest
from siling_voice.backends import SherpaBackend
from siling_voice.cli import read_wav, replay
from siling_voice.config import Settings, model_dir
from siling_voice.models import paths


@pytest.fixture(scope="module")
def real_root():
    if not os.environ.get("SILING_TEST_MODELS"):
        pytest.skip("Set SILING_TEST_MODELS=1 to run real ONNX inference")
    return model_dir()


@pytest.mark.models
def test_official_chinese_sample_kws_vad_asr(real_root, tmp_path):
    files = paths(real_root)
    kws_audio, _ = read_wav(files["kws_tokens"].parent / "test_wavs/zh_3.wav")
    command, _ = read_wav(files["kws_tokens"].parent / "test_wavs/zh_4.wav")
    # Keyword occurs inside a longer sentence. Wait for the discarded tail to
    # finish, then place a second command after a deliberate spoken pause.
    samples = np.concatenate((kws_audio, np.zeros(16000), command, np.zeros(16000)))
    target = tmp_path / "official-composite.wav"
    with wave.open(str(target), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(16000)
        out.writeframes((samples * 32767).astype("<i2").tobytes())
    result = replay(target, Settings(wake_word="法国"))
    assert any(e.get("state") == "WAKE_DETECTED" for e in result["events"])
    assert any(e["type"] == "transcript" for e in result["events"])
    assert result["final_state"] == "IDLE"
    assert result["hardware_acceptance"] == "NOT_VERIFIED"


@pytest.mark.models
def test_official_asr_sample_reports_observed_text(real_root, tmp_path):
    backend = SherpaBackend(real_root, Settings())
    samples, _ = read_wav(paths(real_root)["asr_tokens"].parent / "test_wavs/zh.wav")
    text = backend.transcribe(samples)
    # Quantized model may confuse 开放/开饭; preserve the observed result.
    assert "早上9点至下午5点" in text
    (tmp_path / "observed-asr.json").write_text(
        json.dumps({"text": text}, ensure_ascii=False), "utf-8"
    )


@pytest.mark.models
@pytest.mark.parametrize("speaker", [3, 58])
def test_default_wake_and_chinese_command_on_synthetic_audio(real_root, speaker):
    fixtures = os.environ.get("SILING_TEST_FIXTURES")
    if not fixtures:
        pytest.skip("SILING_TEST_FIXTURES is required for default-keyword acoustic validation")
    result = replay(Path(fixtures) / f"positive-{speaker}.wav", Settings())
    texts = [e["text"] for e in result["events"] if e["type"] == "transcript"]
    assert len(texts) == 1, result
    assert "打开记事本" in texts[0], result
    assert result["final_state"] == "IDLE"


@pytest.mark.models
@pytest.mark.parametrize("fixture", ["noise.wav", "command-only-3.wav", "command-only-58.wav"])
def test_negative_fixtures_do_not_wake(real_root, fixture):
    fixtures = os.environ.get("SILING_TEST_FIXTURES")
    if not fixtures:
        pytest.skip("SILING_TEST_FIXTURES not configured")
    result = replay(Path(fixtures) / fixture, Settings())
    assert not any(e.get("state") == "WAKE_DETECTED" for e in result["events"]), result
    assert not any(e["type"] == "transcript" for e in result["events"]), result


@pytest.mark.models
def test_wake_without_command_times_out_without_transcript(real_root):
    fixtures = os.environ.get("SILING_TEST_FIXTURES")
    if not fixtures:
        pytest.skip("SILING_TEST_FIXTURES not configured")
    result = replay(Path(fixtures) / "wake-only-3.wav", Settings())
    assert any(e.get("state") == "WAKE_DETECTED" for e in result["events"]), result
    assert not any(e["type"] == "transcript" for e in result["events"]), result
    assert result["final_state"] == "IDLE"
