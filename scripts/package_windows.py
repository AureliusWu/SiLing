"""Build the Python sidecar; Tauri's NSIS step consumes the identical binary."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

if sys.platform != "win32":
    raise SystemExit("Windows runner required; cross-packaging is not supported")
subprocess.run([sys.executable, "scripts/make_icon.py"], check=True)
subprocess.run(
    [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onefile",
        "--name",
        "SiLing-Voice",
        "--collect-all",
        "siling_voice",
        "--collect-all",
        "sherpa_onnx",
        "--collect-all",
        "soxr",
        "--collect-all",
        "_sounddevice_data",
        "--collect-all",
        "pypinyin",
        "--icon",
        "apps/desktop/src-tauri/icons/icon.ico",
        "scripts/voice_entry.py",
    ],
    check=True,
)
target = Path("apps/desktop/src-tauri/binaries/SiLing-Voice-x86_64-pc-windows-msvc.exe")
target.parent.mkdir(parents=True, exist_ok=True)
shutil.copy2("dist/SiLing-Voice.exe", target)
