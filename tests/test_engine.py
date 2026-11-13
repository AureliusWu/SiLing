import numpy as np
import pytest
from siling_voice.config import Settings
from siling_voice.engine import FRAME, RATE, Engine, State


class FakeSpeech:
    def __init__(self):
        self.trigger = False
        self.fail_asr = False
        self.audio = None
        self.calls = 0

    def reset(self):
        pass

    def keyword(self, frame):
        wake, self.trigger = self.trigger, False
        return "你好司聆" if wake else ""

    def speech(self, frame):
        return bool(np.max(np.abs(frame)) > 0.05)

    def transcribe(self, samples):
        self.calls += 1
        self.audio = samples.copy()
        if self.fail_asr:
            raise RuntimeError("sensitive transcript must not be exposed")
        return "打开记事本。"


def feed(engine, seconds, speaking=False):
    for _ in range(round(seconds * RATE / FRAME)):
        engine.feed(np.full(FRAME, 0.2 if speaking else 0, dtype=np.float32))


@pytest.fixture
def rig():
    backend, events = FakeSpeech(), []
    engine = Engine(backend, Settings(), events.append)
    engine.start()
    return engine, backend, events


def test_wake_speech_endpoint_transcript_idle(rig):
    engine, backend, events = rig
    backend.trigger = True
    feed(engine, 0.032)
    feed(engine, 1, True)
    feed(engine, 0.8)
    assert engine.state == State.IDLE
    assert backend.calls == 1
    assert [e["text"] for e in events if e["type"] == "transcript"] == ["打开记事本。"]
    assert [e["state"] for e in events if e["type"] == "state"] == [
        "IDLE",
        "WAKE_DETECTED",
        "LISTENING",
        "TRANSCRIBING",
        "IDLE",
    ]


def test_no_keyword_never_transcribes(rig):
    engine, backend, _ = rig
    feed(engine, 20, True)
    assert backend.calls == 0
    assert engine.state == State.IDLE


def test_speech_onset_keeps_preroll(rig):
    engine, backend, _ = rig
    engine.wake()
    feed(engine, 0.3)
    feed(engine, 0.5, True)
    feed(engine, 0.8)
    assert backend.audio[0] == 0
    assert np.max(backend.audio) == pytest.approx(0.2)


def test_silence_wait_timeout_does_not_hallucinate(rig):
    engine, backend, events = rig
    engine.wake()
    feed(engine, 6.1)
    assert engine.state == State.IDLE
    assert backend.calls == 0
    assert any(e.get("reason") == "no_speech" for e in events)


def test_continuous_speech_is_bounded(rig):
    engine, backend, events = rig
    engine.wake()
    feed(engine, 16, True)
    assert backend.calls == 1
    assert len(backend.audio) <= 15 * RATE + FRAME
    assert any(e.get("reason") == "max_duration" for e in events)


def test_click_noise_not_recognized(rig):
    engine, backend, _ = rig
    engine.wake()
    feed(engine, 0.032, True)
    feed(engine, 1)
    assert backend.calls == 0
    assert engine.state == State.IDLE


def test_cancel_discards_entire_recording(rig):
    engine, backend, _ = rig
    engine.wake()
    feed(engine, 0.5, True)
    engine.cancel()
    feed(engine, 1)
    assert backend.calls == 0
    assert not engine.chunks


def test_muted_and_error_states_do_not_process_audio(rig):
    engine, backend, _ = rig
    for state in (State.MUTED, State.ERROR, State.STOPPING):
        engine.transition(state)
        backend.trigger = True
        feed(engine, 1, True)
        assert engine.state == state
    assert backend.calls == 0


def test_asr_error_recovers_without_sensitive_message(rig):
    engine, backend, events = rig
    backend.fail_asr = True
    engine.wake()
    feed(engine, 0.5, True)
    feed(engine, 1)
    assert engine.state == State.IDLE
    assert any(e.get("code") == "ASR_FAILED" for e in events)
    assert "sensitive" not in str(events)


def test_repeated_wake_is_deduplicated_and_cooldown_applies(rig):
    engine, backend, events = rig
    engine.wake()
    engine.wake()
    assert engine.sequence == 1
    engine.cancel()
    backend.trigger = True
    feed(engine, 0.5)
    assert engine.state == State.IDLE
    feed(engine, 0.6)
    assert engine.state == State.LISTENING
    assert len([e for e in events if e.get("state") == "WAKE_DETECTED"]) == 2


def test_bad_frame_fails_early(rig):
    with pytest.raises(ValueError):
        rig[0].feed(np.zeros(10, dtype=np.float32))
