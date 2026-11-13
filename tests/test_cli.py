import os
import subprocess
import sys


def test_chinese_cli_on_ascii_redirected_console():
    result = subprocess.run(
        [sys.executable, "-m", "siling_voice", "--help"],
        env={**os.environ, "PYTHONIOENCODING": "ascii"},
        capture_output=True,
        timeout=15,
    )
    assert result.returncode == 0, result.stderr
    assert "本地中文唤醒" in result.stdout.decode("utf-8")
