from __future__ import annotations

import argparse
import json
import os
import platform
import socket
import sys
import threading
import wave
import webbrowser
from pathlib import Path
from typing import Any

import numpy as np

from . import __version__
from .config import Settings, data_dir, load_settings, model_dir


class InstanceLock:
    def __enter__(self) -> InstanceLock:
        data_dir().mkdir(parents=True, exist_ok=True)
        self.file = (data_dir() / "service.lock").open("a+b")
        self.file.seek(0)
        if self.file.read(1) == b"":
            self.file.write(b"0")
            self.file.flush()
        self.file.seek(0)
        try:
            if sys.platform == "win32":
                import msvcrt

                msvcrt.locking(self.file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(self.file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.file.close()
            raise RuntimeError("SiLing 已运行；请先退出已有实例") from None
        return self

    def __exit__(self, *_: Any) -> None:
        self.file.close()


def read_wav(path: Path) -> tuple[np.ndarray, int]:
    with wave.open(str(path), "rb") as source:
        if source.getsampwidth() != 2 or source.getnchannels() not in {1, 2}:
            raise ValueError("WAV 必须为 PCM16 单声道或双声道")
        if source.getnframes() > source.getframerate() * 120:
            raise ValueError("测试 WAV 最长 120 秒")
        data = np.frombuffer(source.readframes(source.getnframes()), "<i2")
        samples = data.astype(np.float32).reshape(-1, source.getnchannels()).mean(axis=1) / 32768
        return samples, source.getframerate()


def replay(path: Path, settings: Settings, demo: bool = False) -> dict[str, Any]:
    from .audio import FrameConverter
    from .backends import DemoBackend, SherpaBackend
    from .engine import FRAME, Engine

    samples, rate = read_wav(path)
    backend = DemoBackend() if demo else SherpaBackend(model_dir(), settings)
    events: list[dict[str, Any]] = []
    engine = Engine(backend, settings, events.append)
    converter = FrameConverter(rate)
    engine.start()
    # Final silence allows KWS lookahead and VAD endpointing to complete.
    audio = np.concatenate((samples, np.zeros(rate * 2, dtype=np.float32)))
    for offset in range(0, len(audio), FRAME):
        for frame in converter.feed(audio[offset : offset + FRAME]):
            engine.feed(frame)
    return {
        "mode": "demo" if demo else "local",
        "sample_rate": rate,
        "duration_ms": round(len(samples) * 1000 / rate),
        "events": events,
        "final_state": engine.state.value,
        "hardware_acceptance": "NOT_VERIFIED",
    }


def serve(args: argparse.Namespace) -> None:
    import uvicorn

    from .api import create_app
    from .controller import Controller

    settings = load_settings()
    with InstanceLock():
        controller = Controller(settings, model_dir(), args.demo)
        app = create_app(controller)
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        if sys.platform == "win32":
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        sock.bind(("127.0.0.1", args.port))
        sock.listen(128)
        port = sock.getsockname()[1]
        url = f"http://127.0.0.1:{port}"
        server = uvicorn.Server(uvicorn.Config(app, log_level="warning", access_log=False))
        app.state.shutdown = lambda: setattr(server, "should_exit", True)
        ready = Path(args.ready_file) if args.ready_file else None
        if ready:
            fd = os.open(ready, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as out:
                json.dump({"url": url, "token": app.state.token, "pid": os.getpid()}, out)
        elif not args.no_browser:
            destination = args.ui_url or url
            threading.Timer(
                0.7, lambda: webbrowser.open(f"{destination}/#token={app.state.token}&api={url}")
            ).start()
        print(f"SiLing {__version__}: {url} (local audio; microphone initially muted)")
        try:
            server.run(sockets=[sock])
        finally:
            controller.mute(timeout=3)
            sock.close()
            if ready:
                ready.unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="司聆：本地中文唤醒 MVP")
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("serve", help="启动界面和语音服务；默认不采集麦克风")
    run.add_argument("--demo", action="store_true", help="假设备模式；不是模型测试")
    run.add_argument("--port", type=int, default=17653)
    run.add_argument("--no-browser", action="store_true")
    run.add_argument("--ready-file", help=argparse.SUPPRESS)
    run.add_argument("--ui-url", help="开发 UI 地址，例如 http://localhost:1420")
    sub.add_parser("devices", help="枚举输入设备")
    sub.add_parser("doctor", help="检查环境和模型；不获取麦克风")
    model = sub.add_parser("models", help="显式下载/校验模型")
    model.add_argument("operation", choices=["download", "verify", "install"])
    model.add_argument("--from", dest="source", type=Path, help="离线官方归档目录")
    wav = sub.add_parser("wav", help="本地 WAV 完整 KWS -> VAD -> ASR 回放；会输出文本")
    wav.add_argument("path", type=Path)
    wav.add_argument("--wake-word", default="你好司聆")
    wav.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        if args.command == "serve":
            serve(args)
        elif args.command == "devices":
            from .audio import devices

            print(json.dumps(devices(), ensure_ascii=False, indent=2))
        elif args.command == "models":
            from .models import install, verify_installed

            if args.operation == "verify":
                verify_installed(model_dir())
            else:
                if args.operation == "install" and args.source is None:
                    parser.error("models install requires --from")
                install(model_dir(), args.source)
            print("Models: SHA256_VERIFIED")
        elif args.command == "doctor":
            from .audio import AudioFailure, devices
            from .backends import native_versions
            from .models import verify_installed

            report: dict[str, Any] = {
                "version": __version__,
                "os": platform.platform(),
                "python": platform.python_version(),
                "cloud": False,
                "hardware_acceptance": "NOT_VERIFIED",
            }
            try:
                report["dependencies"] = native_versions()
            except Exception:
                report["dependencies"] = "MISSING"
            try:
                verify_installed(model_dir())
                report["models"] = "SHA256_VERIFIED"
            except ValueError:
                report["models"] = "MISSING_OR_CORRUPT"
            try:
                report["input_devices"] = devices()
            except AudioFailure as error:
                report["audio"] = error.code
            print(json.dumps(report, ensure_ascii=False, indent=2))
        elif args.command == "wav":
            result = replay(args.path, Settings(wake_word=args.wake_word))
            rendered = json.dumps(result, ensure_ascii=False, indent=2)
            if args.output:
                args.output.parent.mkdir(parents=True, exist_ok=True)
                args.output.write_text(rendered, "utf-8")
            print(rendered)
            if not any(e["type"] == "transcript" for e in result["events"]):
                sys.exit(1)
    except (ValueError, RuntimeError, OSError) as error:
        print(f"SiLing: {error}", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
