from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

import numpy as np

from .config import Settings
from .engine import RATE, Audio
from .models import paths, verify_installed


def keyword_tokens(word: str, tokens_file: Path) -> str:
    from pypinyin import Style, lazy_pinyin

    # Same ppinyin representation as sherpa-onnx-cli text2token.
    initials = lazy_pinyin(word, style=Style.INITIALS, strict=False)
    finals = lazy_pinyin(word, style=Style.FINALS_TONE, strict=False)
    pieces = [part for pair in zip(initials, finals, strict=True) for part in pair if part]
    vocabulary = {
        line.split()[0] for line in tokens_file.read_text("utf-8").splitlines() if line.strip()
    }
    unknown = set(pieces) - vocabulary
    if unknown:
        raise ValueError("当前关键词模型不支持此唤醒词的拼音；请更换词语")
    return " ".join(pieces) + f" @{word}\n"


class SherpaBackend:
    def __init__(self, root: Path, settings: Settings) -> None:
        import sherpa_onnx as sherpa

        verify_installed(root)
        files = paths(root)
        # Windows cannot reopen a delete-on-close NamedTemporaryFile from C++.
        with tempfile.TemporaryDirectory(prefix="siling-keyword-") as temporary:
            keywords = Path(temporary) / "keywords.txt"
            keywords.write_text(keyword_tokens(settings.wake_word, files["kws_tokens"]), "utf-8")
            self.kws = sherpa.KeywordSpotter(
                tokens=str(files["kws_tokens"]),
                encoder=str(files["encoder"]),
                decoder=str(files["decoder"]),
                joiner=str(files["joiner"]),
                keywords_file=str(keywords),
                keywords_threshold=settings.kws_threshold,
                num_threads=settings.num_threads,
                provider="cpu",
                num_trailing_blanks=1,
            )
        config = sherpa.VadModelConfig()
        config.silero_vad.model = str(files["vad"])
        config.silero_vad.threshold = 0.5
        config.silero_vad.min_speech_duration = 0.064
        config.silero_vad.min_silence_duration = 0.1
        config.silero_vad.window_size = 512
        config.sample_rate = RATE
        config.num_threads = settings.num_threads
        self.vad = sherpa.VoiceActivityDetector(config, buffer_size_in_seconds=35)
        self.asr = sherpa.OfflineRecognizer.from_sense_voice(
            model=str(files["asr"]),
            tokens=str(files["asr_tokens"]),
            num_threads=settings.num_threads,
            use_itn=True,
            language="zh",
            provider="cpu",
        )
        self.reset()

    def reset(self) -> None:
        self.stream = self.kws.create_stream()
        self.vad.reset()

    def keyword(self, frame: Audio) -> str:
        self.stream.accept_waveform(RATE, frame)
        result = ""
        while self.kws.is_ready(self.stream):
            self.kws.decode_stream(self.stream)
            current = self.kws.get_result(self.stream)
            if current:
                result = str(current)
                self.kws.reset_stream(self.stream)
                break
        return result

    def speech(self, frame: Audio) -> bool:
        self.vad.accept_waveform(frame)
        speaking = bool(self.vad.is_speech_detected())
        while not self.vad.empty():
            self.vad.pop()
        return speaking

    def transcribe(self, samples: Audio) -> str:
        stream = self.asr.create_stream()
        stream.accept_waveform(RATE, samples)
        self.asr.decode_stream(stream)
        return str(stream.result.text)


class DemoBackend:
    """Deterministic fake: never presented as real speech recognition."""

    def reset(self) -> None:
        pass

    def keyword(self, frame: Audio) -> str:
        return ""

    def speech(self, frame: Audio) -> bool:
        return bool(np.max(np.abs(frame)) > 0.05)

    def transcribe(self, samples: Audio) -> str:
        return "这是模拟演示文本，未进行真实语音识别。"


def native_versions() -> dict[str, Any]:
    from importlib.metadata import version

    return {name: version(name) for name in ("sherpa-onnx", "sounddevice", "numpy", "pypinyin")}
