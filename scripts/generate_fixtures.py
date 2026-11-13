"""Generate explicit synthetic fixtures, never a substitute for microphone QA.

Usage: python scripts/generate_fixtures.py EXTRACTED_KOKORO_DIR OUTPUT_DIR
Only used during development/CI. No TTS model is shipped with R1.
"""

from __future__ import annotations

import json
import sys
import wave
from pathlib import Path

import numpy as np
import sherpa_onnx as sherpa

root, output = map(Path, sys.argv[1:3])
output.mkdir(parents=True, exist_ok=True)
config = sherpa.OfflineTtsConfig(
    model=sherpa.OfflineTtsModelConfig(
        kokoro=sherpa.OfflineTtsKokoroModelConfig(
            model=str(root / "model.int8.onnx"),
            voices=str(root / "voices.bin"),
            tokens=str(root / "tokens.txt"),
            data_dir=str(root / "espeak-ng-data"),
            lexicon=f"{root / 'lexicon-us-en.txt'},{root / 'lexicon-zh.txt'}",
        ),
        num_threads=2,
    )
)
if not config.validate():
    raise ValueError("invalid Kokoro fixture-generation config")
tts = sherpa.OfflineTts(config)
rate = 24000


def write(name, samples):
    with wave.open(str(output / name), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(rate)
        out.writeframes((np.clip(samples, -1, 1) * 32767).astype("<i2").tobytes())


for sid in (3, 58):
    wake = np.asarray(tts.generate("你好司聆。", sid=sid).samples, dtype=np.float32)
    command = np.asarray(tts.generate("打开记事本。", sid=sid).samples, dtype=np.float32)
    silence = np.zeros(rate, dtype=np.float32)
    write(f"positive-{sid}.wav", np.concatenate((silence / 2, wake, silence, command, silence)))
    write(f"command-only-{sid}.wav", np.concatenate((silence, command, silence)))
    write(f"wake-only-{sid}.wav", np.concatenate((silence, wake, np.zeros(rate * 8))))
write("noise.wav", np.random.default_rng(20261113).normal(0, 0.01, rate * 10))
(output / "provenance.json").write_text(
    json.dumps(
        {
            "type": "synthetic",
            "generator": "sherpa-onnx 2.0.1 / Kokoro v1.1-zh int8",
            "model_sha256": "259c9c8bc906d6078e4e0570421885dabb68b539c2f970fcbb890a58eeaf3e9c",
            "speakers": [3, 58],
            "wake": "你好司聆",
            "command": "打开记事本",
            "hardware_acceptance": "NOT_VERIFIED",
        },
        ensure_ascii=False,
        indent=2,
    ),
    "utf-8",
)
