"""Generate actual Chinese PCM with the frozen Windows Kokoro runtime."""

import json
import subprocess
import sys
import wave
from pathlib import Path

import numpy as np

exe = str(Path(sys.argv[1]).resolve())
subprocess.run([exe, "tts", "download"], check=True, timeout=300)
output = Path(".evidence/frozen-chinese-tts.wav")
subprocess.run(
    [
        exe,
        "tts",
        "synthesize",
        "--text",
        "你好，我是司聆。中文播报测试完成。",
        "--output",
        str(output),
    ],
    check=True,
    timeout=120,
)
with wave.open(str(output), "rb") as source:
    assert source.getnchannels() == 1 and source.getsampwidth() == 2
    rate = source.getframerate()
    samples = np.frombuffer(source.readframes(source.getnframes()), "<i2")
assert rate == 24000 and len(samples) > rate and np.max(np.abs(samples.astype(np.int32))) > 100
Path(".evidence/frozen-tts.json").write_text(
    json.dumps(
        {
            "real_kokoro_pcm": True,
            "sample_rate": rate,
            "duration_s": round(len(samples) / rate, 3),
            "hardware_acceptance": "NOT_VERIFIED",
        },
        indent=2,
    ),
    "utf-8",
)
print("PASS: frozen real Chinese TTS waveform; physical speaker NOT_VERIFIED")
