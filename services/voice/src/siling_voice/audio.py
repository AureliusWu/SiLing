from __future__ import annotations

import queue
import threading
import time
from collections.abc import Iterator
from typing import Any

import numpy as np

from .engine import FRAME, RATE, Audio


class AudioFailure(Exception):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def devices() -> list[dict[str, Any]]:
    try:
        import sounddevice as sd

        default = int(sd.default.device[0])
        return [
            {
                "id": i,
                "name": d["name"],
                "channels": int(d["max_input_channels"]),
                "sample_rate": int(d["default_samplerate"]),
                "default": i == default,
            }
            for i, d in enumerate(sd.query_devices())
            if d["max_input_channels"] > 0
        ]
    except Exception as error:
        raise AudioFailure("AUDIO_UNAVAILABLE") from error


class FrameConverter:
    """Continuous resampling; do not reset a filter at every callback boundary."""

    def __init__(self, native_rate: int) -> None:
        import soxr

        self.resampler = (
            soxr.ResampleStream(native_rate, RATE, 1, dtype="float32", quality="MQ")
            if native_rate != RATE
            else None
        )
        self.pending = np.empty(0, dtype=np.float32)

    def feed(self, samples: Audio) -> Iterator[Audio]:
        chunk = self.resampler.resample_chunk(samples) if self.resampler is not None else samples
        self.pending = np.concatenate((self.pending, chunk))
        while len(self.pending) >= FRAME:
            yield self.pending[:FRAME].copy()
            self.pending = self.pending[FRAME:]


class Microphone:
    def __init__(self, device: int | None) -> None:
        self.device = device
        self.queue: queue.Queue[Audio] = queue.Queue(maxsize=64)
        self.fault = threading.Event()
        self.stream: Any = None

    def __enter__(self) -> Microphone:
        try:
            import sounddevice as sd

            info = sd.query_devices(self.device, "input")
            if info["max_input_channels"] < 1:
                raise AudioFailure("NO_INPUT_DEVICE")
            rate = RATE
            try:
                sd.check_input_settings(
                    device=self.device, channels=1, dtype="float32", samplerate=rate
                )
            except sd.PortAudioError:
                rate = int(info["default_samplerate"])
            self.converter = FrameConverter(rate)

            def callback(indata: Audio, frames: int, timing: Any, status: Any) -> None:
                if status:
                    self.fault.set()
                try:
                    self.queue.put_nowait(indata[:, 0].copy())
                except queue.Full:
                    self.fault.set()

            self.stream = sd.InputStream(
                device=self.device,
                channels=1,
                dtype="float32",
                samplerate=rate,
                blocksize=round(rate * 0.032),
                callback=callback,
            )
            self.stream.start()
            self.last_audio = time.monotonic()
            return self
        except Exception as error:
            self.close()
            if isinstance(error, AudioFailure):
                raise
            raise AudioFailure("MICROPHONE_OPEN_FAILED") from error

    def read(self) -> list[Audio]:
        if self.fault.is_set():
            raise AudioFailure("AUDIO_OVERFLOW_OR_DISCONNECT")
        if self.stream is not None and not self.stream.active:
            raise AudioFailure("DEVICE_DISCONNECTED")
        try:
            samples = self.queue.get(timeout=0.1)
        except queue.Empty:
            if time.monotonic() - self.last_audio > 3:
                raise AudioFailure("DEVICE_STALLED") from None
            return []
        self.last_audio = time.monotonic()
        return list(self.converter.feed(samples))

    def flush(self) -> None:
        while True:
            try:
                self.queue.get_nowait()
            except queue.Empty:
                break
        self.converter = FrameConverter(int(self.stream.samplerate))
        self.fault.clear()
        self.last_audio = time.monotonic()

    def close(self) -> None:
        if self.stream is not None:
            try:
                self.stream.stop()
            finally:
                self.stream.close()
                self.stream = None

    def __exit__(self, *_: Any) -> None:
        self.close()


def play_chime() -> None:
    try:
        import sounddevice as sd

        rate = 24000
        t = np.arange(int(rate * 0.09), dtype=np.float32) / rate
        tone = 0.09 * np.sin(2 * np.pi * 880 * t) * np.sin(np.pi * t / 0.09) ** 2
        sd.play(tone.astype(np.float32), rate, blocking=True)
    except Exception:
        # A missing output device must not stop transcription.
        return
