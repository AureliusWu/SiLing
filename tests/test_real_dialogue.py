import os
import threading
from pathlib import Path

import numpy as np
import pytest
from siling_voice.cli import replay
from siling_voice.config import Settings, model_dir
from siling_voice.dialogue import Dialogue
from siling_voice.providers import Cancelled
from siling_voice.tts import Kokoro, Speaker


@pytest.fixture(scope="module")
def kokoro():
    if not os.environ.get("SILING_TEST_TTS"):
        pytest.skip("SILING_TEST_TTS=1 and installed Kokoro required")
    return Kokoro(model_dir(), Settings())


@pytest.mark.models
def test_real_asr_mock_llm_real_chinese_tts_three_turns(kokoro):
    fixtures = os.environ.get("SILING_TEST_FIXTURES")
    if not fixtures:
        pytest.skip("speech fixtures required")
    events, captured = [], []
    settings = Settings(provider="mock", tts="kokoro")

    class Sink(Speaker):
        def play(self, samples, rate, cancel):
            assert rate == 24000 and np.all(np.isfinite(samples))
            assert len(samples) > rate // 2
            captured.append({"samples": len(samples), "rate": rate})

    speaker = Sink(model_dir(), settings)
    speaker.kokoro = kokoro
    dialogue = Dialogue(settings, model_dir(), events.append, speaker=speaker)
    for _ in range(3):
        result = replay(Path(fixtures) / "positive-3.wav", settings)
        text = [e["text"] for e in result["events"] if e["type"] == "transcript"]
        assert text == ["打开记事本。"]
        dialogue.submit(text[0])
        dialogue.thread.join(30)
        assert not dialogue.active
        assert dialogue.last_metrics["outcome"] == "ok"
    assert len(captured) == 3 and len(dialogue.history) == 6
    assert [e["text"] for e in events if e["type"] == "assistant"][-1].startswith("这是第3轮")


@pytest.mark.models
def test_real_tts_cancel_callback(kokoro):
    cancel = threading.Event()
    timer = threading.Timer(0.02, cancel.set)
    timer.start()
    try:
        with pytest.raises(Cancelled):
            kokoro.generate("这是一段用于验证打断的中文语音。" * 10, cancel)
    finally:
        timer.cancel()
