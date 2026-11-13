"""Run the installed native host, restart its sidecar, and uninstall on CI only."""

from __future__ import annotations

import ctypes
import json
import os
import subprocess
import tempfile
import time
import urllib.request
from pathlib import Path


def alive(pid: int) -> bool:
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = [ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32]
    kernel.OpenProcess.restype = ctypes.c_void_p
    kernel.CloseHandle.argtypes = [ctypes.c_void_p]
    handle = kernel.OpenProcess(0x1000, False, pid)
    if not handle:
        return False
    kernel.GetExitCodeProcess.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint32)]
    code = ctypes.c_uint32()
    result = kernel.GetExitCodeProcess(handle, ctypes.byref(code))
    kernel.CloseHandle(handle)
    return bool(result and code.value == 259)


def wait_ready(child, ready):
    until = time.monotonic() + 45
    while time.monotonic() < until:
        if child.poll() is not None:
            raise RuntimeError("service exited before readiness")
        if ready.exists():
            try:
                connection = json.loads(ready.read_text("utf-8"))
                call(connection, "/api/status")
                return connection
            except (OSError, ValueError):
                pass
        time.sleep(0.1)
    raise RuntimeError("service readiness timeout")


def call(connection, path, payload=None):
    headers = {"Authorization": "Bearer " + connection["token"]}
    if payload is not None:
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(
        connection["url"] + path,
        data=None if payload is None else json.dumps(payload).encode(),
        headers=headers,
    )
    with urllib.request.urlopen(request, timeout=5) as response:
        return json.loads(response.read())


def main():
    if os.name != "nt" or os.environ.get("GITHUB_ACTIONS") != "true":
        raise SystemExit("isolated Windows GitHub runner required")
    import winreg

    (installer,) = Path("apps/desktop/src-tauri/target/release/bundle/nsis").glob("*-setup.exe")
    result = {"hardware_acceptance": "NOT_VERIFIED"}
    with tempfile.TemporaryDirectory(prefix="siling-install-") as temporary:
        root = Path(temporary)
        folder = root / "installed"
        environment = {**os.environ, "SILING_CONFIG_DIR": str(root / "config")}
        subprocess.run([str(installer.resolve()), "/S", f"/D={folder}"], check=True, timeout=120)
        voice = folder / "SiLing-Voice.exe"
        desktop = folder / "SiLing.exe"
        assert voice.is_file() and desktop.is_file(), list(folder.glob("*"))
        result["silent_install"] = True
        ready = root / "ready.json"
        child = subprocess.Popen(
            [
                str(voice),
                "serve",
                "--demo",
                "--no-browser",
                "--port",
                "0",
                "--ready-file",
                str(ready),
            ],
            env=environment,
        )
        try:
            connection = wait_ready(child, ready)
            call(connection, "/api/desktop/autostart", {"enabled": True})
            assert call(connection, "/api/status")["autostart"]
            call(connection, "/api/control", {"action": "exit"})
            assert child.wait(timeout=15) == 0
            result["autostart_registry"] = True
        finally:
            if child.poll() is None:
                child.kill()
                child.wait()
        report = Path(".evidence/native-desktop.json").resolve()
        report.parent.mkdir(exist_ok=True)
        child = subprocess.Popen(
            [str(folder / "SiLing.exe"), "--smoke-report", str(report)], env=environment
        )
        try:
            assert child.wait(timeout=90) == 0
        finally:
            if child.poll() is None:
                child.kill()
                child.wait()
        native = json.loads(report.read_text("utf-8"))
        for key in (
            "native_start",
            "initial_muted",
            "service_restart",
            "mini_window",
            "diagnostic_download",
        ):
            assert native[key] is True, native
        time.sleep(1)
        assert not alive(native["initial_service_pid"]), native
        assert not alive(native["recovered_service_pid"]), native
        native["no_orphan_server"] = True
        report.write_text(json.dumps(native, indent=2), "utf-8")
        (uninstaller,) = folder.glob("*uninstall*.exe")
        subprocess.run([str(uninstaller), "/S"], check=True, timeout=60)
        until = time.monotonic() + 30
        while voice.exists() and time.monotonic() < until:
            time.sleep(0.2)
        assert not voice.exists() and not desktop.exists()
        try:
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run"
            ) as key:
                winreg.QueryValueEx(key, "SiLing")
            raise AssertionError("autostart registry entry survived uninstall")
        except FileNotFoundError:
            pass
        result["silent_uninstall"] = result["autostart_cleanup"] = True
    Path(".evidence/windows-install.json").write_text(json.dumps(result, indent=2), "utf-8")
    print("PASS: installer, native restart/mini/diagnostics, orphan and autostart cleanup")


if __name__ == "__main__":
    main()
