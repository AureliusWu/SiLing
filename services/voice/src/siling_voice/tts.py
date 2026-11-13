from __future__ import annotations

import base64
import contextlib
import json
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from pathlib import Path
from typing import Any

import numpy as np

from .config import Settings
from .models import check_asset, safe_extract, sha256
from .providers import Cancelled

TTS_ASSET: dict[str, Any] = {
    "filename": "kokoro.tar.bz2",
    "bytes": 147052523,
    "sha256": "259c9c8bc906d6078e4e0570421885dabb68b539c2f970fcbb890a58eeaf3e9c",
    "url": "https://github.com/k2-fsa/sherpa-onnx/releases/download/tts-models/kokoro-int8-multi-lang-v1_1.tar.bz2",
    "directory": "kokoro-int8-multi-lang-v1_1",
}


def install_tts(root: Path, source: Path | None = None) -> None:
    root.mkdir(parents=True, exist_ok=True)
    cache = root / ".downloads"
    cache.mkdir(exist_ok=True)
    archive = source or cache / "kokoro.tar.bz2"
    if source is None and not archive.exists():
        partial = archive.with_suffix(".part")
        try:
            with (
                urllib.request.urlopen(TTS_ASSET["url"], timeout=60) as response,
                partial.open("wb") as out,
            ):
                total = 0
                while chunk := response.read(1024 * 1024):
                    total += len(chunk)
                    if total > TTS_ASSET["bytes"]:
                        raise ValueError("TTS_DOWNLOAD_TOO_LARGE")
                    out.write(chunk)
            check_asset(partial, TTS_ASSET)
            partial.replace(archive)
        finally:
            partial.unlink(missing_ok=True)
    check_asset(archive, TTS_ASSET)
    with tempfile.TemporaryDirectory(prefix=".tts-", dir=root) as temporary:
        staging = Path(temporary)
        safe_extract(archive, staging, TTS_ASSET["directory"])
        model = staging / TTS_ASSET["directory"]
        receipt = {
            "archive": TTS_ASSET["sha256"],
            "files": {
                p.relative_to(model).as_posix(): sha256(p) for p in model.rglob("*") if p.is_file()
            },
        }
        (model / "siling-receipt.json").write_text(json.dumps(receipt), "utf-8")
        target = root / TTS_ASSET["directory"]
        if target.exists():
            shutil.rmtree(target)
        shutil.move(str(model), target)


def verify_tts(root: Path) -> Path:
    directory = root / TTS_ASSET["directory"]
    try:
        receipt = json.loads((directory / "siling-receipt.json").read_text("utf-8"))
        if receipt["archive"] != TTS_ASSET["sha256"]:
            raise ValueError("TTS_CHECKSUM_FAILED")
        for name, digest in receipt["files"].items():
            candidate = directory / name
            if (
                not candidate.resolve().is_relative_to(directory.resolve())
                or sha256(candidate) != digest
            ):
                raise ValueError("TTS_CHECKSUM_FAILED")
        for name in ("model.int8.onnx", "voices.bin", "tokens.txt", "lexicon-zh.txt"):
            if name not in receipt["files"]:
                raise ValueError("TTS_CHECKSUM_FAILED")
    except (OSError, KeyError, json.JSONDecodeError):
        raise ValueError("TTS_MODEL_MISSING") from None
    return directory


class Kokoro:
    def __init__(self, root: Path, settings: Settings) -> None:
        import sherpa_onnx as sherpa

        directory = verify_tts(root)
        config = sherpa.OfflineTtsConfig(
            model=sherpa.OfflineTtsModelConfig(
                kokoro=sherpa.OfflineTtsKokoroModelConfig(
                    model=str(directory / "model.int8.onnx"),
                    voices=str(directory / "voices.bin"),
                    tokens=str(directory / "tokens.txt"),
                    data_dir=str(directory / "espeak-ng-data"),
                    lexicon=f"{directory / 'lexicon-us-en.txt'},{directory / 'lexicon-zh.txt'}",
                ),
                num_threads=settings.num_threads,
            )
        )
        self.engine = sherpa.OfflineTts(config)
        self.settings = settings

    def generate(self, text: str, cancel: threading.Event) -> tuple[np.ndarray, int]:
        if cancel.is_set():
            raise Cancelled()
        audio = self.engine.generate(
            text[:600],
            sid=self.settings.tts_speaker,
            speed=self.settings.tts_speed,
            callback=lambda samples, progress: 0 if cancel.is_set() else 1,
        )
        if cancel.is_set():
            raise Cancelled()
        return np.asarray(audio.samples, dtype=np.float32), int(audio.sample_rate)


class Speaker:
    def __init__(self, root: Path, settings: Settings) -> None:
        self.root, self.settings = root, settings
        self.kokoro: Kokoro | None = None
        self.stream: Any = None

    def stop(self) -> None:
        if self.stream is not None:
            with contextlib.suppress(Exception):
                self.stream.abort()

    def speak(self, text: str, cancel: threading.Event) -> str:
        mode = self.settings.tts
        if mode in {"off", "mock"}:
            if cancel.is_set():
                raise Cancelled()
            return mode
        if mode == "kokoro":
            try:
                if self.kokoro is None:
                    self.kokoro = Kokoro(self.root, self.settings)
                samples, rate = self.kokoro.generate(text, cancel)
                self.play(samples, rate, cancel)
                return "kokoro"
            except Cancelled:
                raise
            except Exception:
                if sys.platform != "win32":
                    raise RuntimeError("LOCAL_TTS_FAILED") from None
                self.system(text, cancel)
                return "system_fallback"
        self.system(text, cancel)
        return "system"

    def play(self, samples: np.ndarray, rate: int, cancel: threading.Event) -> None:
        import sounddevice as sd

        if cancel.is_set():
            raise Cancelled()
        try:
            with sd.OutputStream(samplerate=rate, channels=1, dtype="float32") as stream:
                self.stream = stream
                for start in range(0, len(samples), 1024):
                    if cancel.is_set():
                        stream.abort()
                        raise Cancelled()
                    stream.write(samples[start : start + 1024].reshape(-1, 1))
        finally:
            self.stream = None

    @staticmethod
    def system(text: str, cancel: threading.Event) -> None:
        if sys.platform != "win32":
            raise RuntimeError("SYSTEM_TTS_WINDOWS_ONLY")
        # Constant trusted script. User/model text is stdin JSON, never PowerShell code.
        script = """[Console]::InputEncoding = [System.Text.UTF8Encoding]::new()
$request = [Console]::In.ReadToEnd() | ConvertFrom-Json
Add-Type -AssemblyName System.Speech
$voice = [System.Speech.Synthesis.SpeechSynthesizer]::new()
$cn = $voice.GetInstalledVoices() | Where-Object {
    $_.Enabled -and $_.VoiceInfo.Culture.Name -eq 'zh-CN'
} | Select-Object -First 1
if (!$cn) { exit 5 }
$voice.SelectVoice($cn.VoiceInfo.Name)
$voice.Speak([string]$request.text)
$voice.Dispose()
"""
        encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
        child = subprocess.Popen(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded],
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=0x08000000,
        )
        try:
            assert child.stdin is not None
            child.stdin.write(json.dumps({"text": text[:600]}, ensure_ascii=False).encode("utf-8"))
            child.stdin.close()
            deadline = time.monotonic() + 90
            while child.poll() is None:
                if cancel.wait(0.05):
                    raise Cancelled()
                if time.monotonic() > deadline:
                    raise RuntimeError("SYSTEM_TTS_TIMEOUT")
            if child.returncode != 0:
                raise RuntimeError("SYSTEM_CHINESE_VOICE_UNAVAILABLE")
        finally:
            if child.poll() is None:
                child.terminate()
                child.wait(timeout=5)
