"""Run the exact same UI/service used by the Windows portable build."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
os.chdir(root)
if not (root / "services/voice/src/siling_voice/web/index.html").exists():
    subprocess.run(["npm.cmd" if os.name == "nt" else "npm", "run", "build"], check=True)
subprocess.run([sys.executable, "-m", "siling_voice", "serve", *sys.argv[1:]], check=True)
