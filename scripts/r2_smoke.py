"""Actual loopback HTTP provider, API and three turns; never calls a cloud."""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--frozen", type=Path)
args = parser.parse_args()
requests = []
slow = threading.Event()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_POST(self):
        request = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        requests.append(request)
        if request["messages"][-1]["content"] == "慢请求":
            slow.set()
            time.sleep(2)
        response = json.dumps(
            {"choices": [{"message": {"content": "这是中文协议测试回复。"}}]}, ensure_ascii=False
        ).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(response)))
        self.end_headers()
        with contextlib.suppress(BrokenPipeError, ConnectionResetError):
            self.wfile.write(response)


server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
threading.Thread(target=server.serve_forever, daemon=True).start()
with tempfile.TemporaryDirectory() as temporary:
    ready = Path(temporary) / "ready.json"
    command = (
        [str(args.frozen.resolve())] if args.frozen else [sys.executable, "-m", "siling_voice"]
    )
    child = subprocess.Popen(
        [*command, "serve", "--demo", "--no-browser", "--port", "0", "--ready-file", str(ready)],
        env={**os.environ, "SILING_CONFIG_DIR": str(Path(temporary) / "config")},
    )
    try:
        until = time.monotonic() + 30
        while not ready.exists():
            if child.poll() is not None or time.monotonic() > until:
                raise RuntimeError("R2 service did not start")
            time.sleep(0.1)
        info = json.loads(ready.read_text("utf-8"))

        def api(path, body=None, method=None):
            req = urllib.request.Request(
                info["url"] + "/api/" + path,
                data=json.dumps(body).encode() if body is not None else None,
                headers={
                    "Authorization": "Bearer " + info["token"],
                    "Content-Type": "application/json",
                },
                method=method,
            )
            with urllib.request.urlopen(req, timeout=10) as response:
                return json.load(response)

        time.sleep(0.3)
        api(
            "settings",
            {
                "provider": "compatible",
                "api_base": f"http://127.0.0.1:{server.server_port}/v1",
                "tts": "mock",
            },
            "PUT",
        )

        def wait_done(expected):
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                status = api("status")
                if (
                    not status["dialogue_active"]
                    and len([e for e in status["events"] if e["type"] == "assistant"]) == expected
                ):
                    return status
                time.sleep(0.05)
            raise RuntimeError("Dialogue did not finish correctly")

        for index, text in enumerate(["第一轮", "第二轮", "第三轮"], 1):
            api("chat", {"text": text})
            status = wait_done(index)
            assert status["state"] == "MUTED" and not status["running"]
        assert [len(r["messages"]) for r in requests] == [2, 4, 6]
        api("chat", {"text": "慢请求"})
        assert slow.wait(3)
        api("control", {"action": "cancel"})
        wait_done(3)
        api("chat", {"text": "取消后恢复"})
        wait_done(4)
        api("control", {"action": "clear"})
        assert not api("status")["events"]
        api("control", {"action": "exit"})
        assert child.wait(timeout=10) == 0
        print(
            "PASS: real HTTP provider, three Chinese turns, "
            "context, cancellation, recovery and exit"
        )
    finally:
        if child.poll() is None:
            child.kill()
            child.wait()
        server.shutdown()
        server.server_close()
