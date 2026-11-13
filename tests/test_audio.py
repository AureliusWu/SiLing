import numpy as np
import pytest
from siling_voice.audio import AudioFailure, FrameConverter, Microphone
from siling_voice.engine import FRAME, RATE


@pytest.mark.parametrize("rate", [16000, 44100, 48000])
def test_continuous_native_rate_conversion(rate):
    convert = FrameConverter(rate)
    frames = []
    samples = np.sin(2 * np.pi * 440 * np.arange(rate * 2) / rate).astype(np.float32)
    for offset in range(0, len(samples), 777):
        frames.extend(convert.feed(samples[offset : offset + 777]))
    assert frames
    assert all(len(x) == FRAME and x.dtype == np.float32 for x in frames)
    result = np.concatenate(frames)
    assert RATE * 1.9 < len(result) <= RATE * 2
    assert np.max(np.abs(result)) <= 1.1


def test_callback_overflow_is_reported():
    mic = Microphone(None)
    mic.fault.set()
    with pytest.raises(AudioFailure, match="AUDIO_OVERFLOW_OR_DISCONNECT"):
        mic.read()


def test_inactive_device_is_reported():
    class Device:
        active = False

    mic = Microphone(None)
    mic.stream = Device()
    with pytest.raises(AudioFailure, match="DEVICE_DISCONNECTED"):
        mic.read()
