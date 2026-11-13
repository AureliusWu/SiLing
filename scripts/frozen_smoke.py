"""Verify the packaged HTTP UI, token boundary, fake audio and clean shutdown."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

executable = Path(sys.argv[1]).resolve()
with tempfile.TemporaryDirectory() as temporary:
    ready = Path(temporary) / "ready.json"
    child = subprocess.Popen(
        [
            str(executable),
            "serve",
            "--demo",
            "--no-browser",
            "--port",
            "0",
            "--ready-file",
            str(ready),
        ]
    )
    try:
        until = time.monotonic() + 30
        while not ready.exists() and time.monotonic() < until:
            if child.poll() is not None:
                raise RuntimeError("packaged process exited before readiness")
            time.sleep(0.1)
        connection = json.loads(ready.read_text("utf-8"))

        def request(path, payload=None, auth=True):
            headers = {"Authorization": "Bearer " + connection["token"]} if auth else {}
            if payload is not None:
                headers["Content-Type"] = "application/json"
            req = urllib.request.Request(
                connection["url"] + path,
                data=None if payload is None else json.dumps(payload).encode(),
                headers=headers,
            )
            with urllib.request.urlopen(req, timeout=5) as response:
                return response.read()

        until = time.monotonic() + 10
        while True:
            try:
                index = request("/")
                break
            except (OSError, urllib.error.URLError):
                if time.monotonic() > until:
                    raise
                time.sleep(0.1)
        assert b'<div id="root">' in index
        try:
            request("/api/status", auth=False)
            raise AssertionError("unauthorized API request was accepted")
        except urllib.error.HTTPError as error:
            assert error.code == 401
        request("/api/control", {"action": "start"})
        time.sleep(0.3)
        request("/api/control", {"action": "wake"})
        until = time.monotonic() + 10
        while True:
            status = json.loads(request("/api/status"))
            if any(e["type"] == "transcript" for e in status["events"]):
                break
            assert time.monotonic() < until, status
            time.sleep(0.1)
        assert status["mode"] == "demo"
        request("/api/control", {"action": "mute"})
        assert json.loads(request("/api/status"))["state"] == "MUTED"
        import io
        import zipfile

        with zipfile.ZipFile(io.BytesIO(request("/api/diagnostics/download"))) as archive:
            assert archive.namelist() == ["diagnostics.json"]
            report = json.loads(archive.read("diagnostics.json"))
            assert report["hardware_acceptance"] == "NOT_VERIFIED"
        request("/api/control", {"action": "exit"})
        assert child.wait(timeout=10) == 0
        assert not ready.exists()
        print("PASS: frozen UI, authorization, fake audio closure and process exit")
    finally:
        if child.poll() is None:
            child.kill()
            child.wait()
