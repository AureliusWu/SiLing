"""Single-owner, sample-clock-driven KWS -> endpoint -> ASR state machine.

No device, web, disk or network I/O here. Native adapters are injected, so tests use
the same recorder and transitions as microphone and WAV playback.
"""

from __future__ import annotations

import time
from collections import deque
from collections.abc import Callable
from enum import StrEnum
from typing import Any, Protocol

import numpy as np
from numpy.typing import NDArray

from .config import Settings

Audio = NDArray[np.float32]
RATE = 16000
FRAME = 512


class State(StrEnum):
    IDLE = "IDLE"
    WAKE_DETECTED = "WAKE_DETECTED"
    LISTENING = "LISTENING"
    TRANSCRIBING = "TRANSCRIBING"
    THINKING = "THINKING"
    ACTING = "ACTING"
    SPEAKING = "SPEAKING"
    MUTED = "MUTED"
    ERROR = "ERROR"
    STOPPING = "STOPPING"


class Backend(Protocol):
    def keyword(self, frame: Audio) -> str: ...
    def speech(self, frame: Audio) -> bool: ...
    def transcribe(self, samples: Audio) -> str: ...
    def reset(self) -> None: ...


class Engine:
    def __init__(
        self,
        backend: Backend,
        settings: Settings,
        emit: Callable[[dict[str, Any]], None],
        chime: Callable[[], None] | None = None,
    ) -> None:
        self.backend, self.settings, self.emit = backend, settings, emit
        self.chime = chime or (lambda: None)
        self.state = State.MUTED
        self.clock = 0
        self.ignore_until = 0
        self.sequence = 0
        self.cancelled_audio = False
        self.ptt = False
        self._clear_recording()

    def _clear_recording(self) -> None:
        self.chunks: list[Audio] = []
        self.preroll: deque[Audio] = deque(maxlen=10)
        self.elapsed = self.voiced = self.quiet = 0

    def transition(self, state: State, reason: str = "") -> None:
        previous = self.state
        self.state = state
        self.emit(
            {
                "type": "state",
                "state": state.value,
                "previous": previous.value,
                "reason": reason,
                "session": self.sequence,
            }
        )

    def start(self) -> None:
        self._clear_recording()
        self.backend.reset()
        self.transition(State.IDLE)

    def cancel(self, mute: bool = False) -> None:
        self.ptt = False
        self.cancelled_audio = True
        self._clear_recording()
        self.backend.reset()
        self.ignore_until = self.clock + self.settings.cooldown_ms * RATE // 1000
        self.transition(State.MUTED if mute else State.IDLE, "cancelled")

    def wake(self, manual: bool = False) -> None:
        if self.state != State.IDLE:
            return
        self.sequence += 1
        self._clear_recording()
        self.backend.reset()
        self.transition(State.WAKE_DETECTED, "manual" if manual else self.settings.wake_word)
        # The owner pauses capture delivery and flushes the chime/ASR backlog.
        self.chime()
        self.transition(State.LISTENING)

    def fail(self, code: str) -> None:
        self._clear_recording()
        self.emit({"type": "error", "code": code})
        self.transition(State.ERROR, code)

    def begin_ptt(self) -> None:
        self.wake(manual=True)
        self.ptt = self.state == State.LISTENING

    def end_ptt(self) -> None:
        if self.ptt and self.state == State.LISTENING:
            self.ptt = False
            self._finish("push_to_talk_release")

    def feed(self, frame: Audio) -> None:
        if len(frame) != FRAME:
            raise ValueError(f"expected {FRAME} mono float samples")
        self.clock += len(frame)
        if self.state == State.IDLE:
            if self.clock >= self.ignore_until and self.backend.keyword(frame):
                self.wake()
            return
        if self.state != State.LISTENING:
            return
        self.elapsed += len(frame)
        speaking = self.backend.speech(frame)
        if not self.chunks:
            self.preroll.append(frame.copy())
            if speaking:
                self.chunks.extend(self.preroll)
                self.preroll.clear()
        else:
            self.chunks.append(frame.copy())
        if speaking:
            self.voiced += len(frame)
            self.quiet = 0
        elif self.chunks:
            self.quiet += len(frame)
        if (
            not self.ptt
            and not self.chunks
            and self.elapsed >= self.settings.speech_wait_ms * RATE // 1000
        ):
            self._finish("no_speech")
        elif self.elapsed >= self.settings.max_record_ms * RATE // 1000:
            self._finish("max_duration")
        elif not self.ptt and self.chunks and self.quiet >= self.settings.silence_ms * RATE // 1000:
            self._finish("silence")

    def _finish(self, reason: str) -> None:
        if self.voiced < self.settings.min_speech_ms * RATE // 1000:
            self.emit({"type": "endpoint", "reason": "no_speech", "session": self.sequence})
            self.cancel()
            return
        samples = np.concatenate(self.chunks)
        self.emit(
            {
                "type": "endpoint",
                "reason": reason,
                "audio_ms": round(len(samples) * 1000 / RATE),
                "session": self.sequence,
            }
        )
        self._clear_recording()
        self.transition(State.TRANSCRIBING)
        started = time.perf_counter()
        try:
            text = self.backend.transcribe(samples).strip()
            if text:
                self.emit(
                    {
                        "type": "transcript",
                        "text": text,
                        "session": self.sequence,
                        "asr_ms": round((time.perf_counter() - started) * 1000, 1),
                    }
                )
            else:
                self.emit({"type": "error", "code": "EMPTY_TRANSCRIPT"})
        except Exception:
            # Do not echo exception messages: they can include paths or user data.
            self.emit({"type": "error", "code": "ASR_FAILED"})
        finally:
            self.cancel()
