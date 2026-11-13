from __future__ import annotations

import queue
import threading
import time
from collections import deque
from pathlib import Path
from typing import Any

import numpy as np

from .audio import AudioFailure, Microphone, devices, play_chime
from .backends import DemoBackend, SherpaBackend
from .config import Settings, save_settings
from .engine import FRAME, Engine, State


class Controller:
    def __init__(self, settings: Settings, models: Path, demo: bool = False) -> None:
        self.settings, self.models, self.demo = settings, models, demo
        self.lock = threading.RLock()
        self.stop_event = threading.Event()
        self.cancel_output = threading.Event()
        self.commands: queue.Queue[str] = queue.Queue(maxsize=16)
        self.thread: threading.Thread | None = None
        self.mic: Microphone | None = None
        self.state = State.MUTED.value
        self.events: deque[dict[str, Any]] = deque(maxlen=128)
        self.counter = 0
        self.level = 0.0
        self.loading = False

    def emit(self, event: dict[str, Any]) -> None:
        with self.lock:
            if self.stop_event.is_set() or (
                self.cancel_output.is_set() and event["type"] == "transcript"
            ):
                return
            if event["type"] == "state":
                self.state = event["state"]
            self.counter += 1
            self.events.append({**event, "id": self.counter, "at": time.time()})

    def snapshot(self, after: int = 0) -> dict[str, Any]:
        with self.lock:
            return {
                "state": self.state,
                "level": self.level,
                "loading": self.loading,
                "mode": "demo" if self.demo else "local",
                "cloud": False,
                "hardware_acceptance": "NOT_VERIFIED",
                "settings": self.settings.model_dump(),
                "event_id": self.counter,
                "events": [e.copy() for e in self.events if e["id"] > after],
                "models_installed": (self.models / "installed.json").is_file(),
                "running": self.thread is not None and self.thread.is_alive(),
            }

    def start(self) -> None:
        with self.lock:
            if self.thread is not None and self.thread.is_alive():
                if self.stop_event.is_set():
                    raise RuntimeError("SERVICE_STOPPING")
                return
            self.stop_event.clear()
            self.cancel_output.clear()
            self.commands = queue.Queue(maxsize=16)
            self.loading = True
            self.thread = threading.Thread(target=self._run, name="siling-audio", daemon=True)
            self.thread.start()

    def mute(self, timeout: float = 0.25) -> None:
        self.stop_event.set()
        with self.lock:
            mic, self.mic = self.mic, None
            self.state, self.level = State.MUTED.value, 0.0
            self.events.clear()  # Clear transient transcripts on mute, too.
        if mic is not None:
            mic.close()
        if self.thread is not None:
            self.thread.join(timeout=timeout)

    def command(self, action: str) -> None:
        if action not in {"wake", "cancel"}:
            raise ValueError("UNKNOWN_ACTION")
        if self.thread is None or not self.thread.is_alive() or self.stop_event.is_set():
            raise RuntimeError("NOT_LISTENING")
        if action == "cancel":
            self.cancel_output.set()
        try:
            self.commands.put_nowait(action)
        except queue.Full as error:
            raise RuntimeError("CONTROL_BUSY") from error

    def update(self, settings: Settings) -> None:
        self.mute()
        if self.thread is not None and self.thread.is_alive():
            raise RuntimeError("SERVICE_STOPPING")
        if (self.models / "installed.json").is_file():
            from .backends import keyword_tokens
            from .models import paths

            keyword_tokens(settings.wake_word, paths(self.models)["kws_tokens"])
        save_settings(settings)
        self.settings = settings

    def clear(self) -> None:
        with self.lock:
            self.events.clear()

    def _commands(self, engine: Engine) -> None:
        while True:
            try:
                action = self.commands.get_nowait()
            except queue.Empty:
                return
            if action == "cancel":
                engine.cancel()
                self.cancel_output.clear()
            elif action == "wake":
                engine.wake(manual=True)

    def _run(self) -> None:
        try:
            backend = DemoBackend() if self.demo else SherpaBackend(self.models, self.settings)
            engine = Engine(backend, self.settings, self.emit)
            if self.stop_event.is_set():
                return
            if self.demo:
                self.loading = False
                engine.start()
                voiced = 0
                while not self.stop_event.wait(0.032):
                    self._commands(engine)
                    if engine.state == State.LISTENING:
                        voiced += 1
                        frame = np.full(FRAME, 0.2 if voiced < 32 else 0, dtype=np.float32)
                    else:
                        voiced = 0
                        frame = np.zeros(FRAME, dtype=np.float32)
                    self.level = float(np.sqrt(np.mean(frame * frame)))
                    engine.feed(frame)
                return
            for attempt in range(4):
                if self.stop_event.is_set():
                    break
                try:
                    with Microphone(self.settings.device) as mic:
                        with self.lock:
                            if self.stop_event.is_set():
                                return
                            self.mic = mic
                            self.loading = False

                        def chime() -> None:
                            if self.settings.chime:
                                play_chime()
                            mic.flush()

                        engine.chime = chime
                        engine.start()
                        while not self.stop_event.is_set():
                            self._commands(engine)
                            for frame in mic.read():
                                if self.stop_event.is_set():
                                    break
                                self.level = min(1.0, float(np.sqrt(np.mean(frame * frame))) * 5)
                                before = engine.state
                                engine.feed(frame)
                                if before != engine.state or engine.cancelled_audio:
                                    engine.cancelled_audio = False
                                    mic.flush()
                                    break
                        break
                except AudioFailure as error:
                    if self.stop_event.is_set():
                        break
                    engine.fail(error.code)
                    if attempt == 3 or self.stop_event.wait(0.5 * (attempt + 1)):
                        break
                finally:
                    with self.lock:
                        self.mic = None
        except ValueError:
            self.emit({"type": "error", "code": "MODELS_OR_KEYWORD_INVALID"})
            self.emit({"type": "state", "state": State.ERROR.value})
        except Exception:
            self.emit({"type": "error", "code": "ENGINE_INIT_OR_RUNTIME_FAILED"})
            self.emit({"type": "state", "state": State.ERROR.value})
        finally:
            self.loading = False
            self.level = 0.0

    def list_devices(self) -> list[dict[str, Any]]:
        if self.demo:
            return [
                {
                    "id": 0,
                    "name": "模拟设备（不采集麦克风）",
                    "channels": 1,
                    "sample_rate": 16000,
                    "default": True,
                }
            ]
        return devices()
