"""Small Windows API boundary; no commands or user-provided scripts."""

from __future__ import annotations

import contextlib
import ctypes
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any


def get_autostart() -> bool:
    if sys.platform != "win32":
        return False
    import winreg

    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run"
        ) as key:
            value, _ = winreg.QueryValueEx(key, "SiLing")
            return bool(value)
    except OSError:
        return False


def set_autostart(enabled: bool) -> None:
    if sys.platform != "win32":
        raise RuntimeError("AUTOSTART_WINDOWS_ONLY")
    import winreg

    with winreg.CreateKey(
        winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run"
    ) as key:
        if enabled:
            executable = Path(sys.executable).resolve().with_name("SiLing.exe")
            if not getattr(sys, "frozen", False) or not executable.is_file():
                raise RuntimeError("AUTOSTART_PACKAGED_DESKTOP_REQUIRED")
            winreg.SetValueEx(
                key,
                "SiLing",
                0,
                winreg.REG_SZ,
                subprocess.list2cmdline([str(executable), "--background"]),
            )
        else:
            with contextlib.suppress(FileNotFoundError):
                winreg.DeleteValue(key, "SiLing")


def discover_apps() -> list[dict[str, str]]:
    if sys.platform != "win32":
        return []
    import os

    roots = [
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs",
        Path(os.environ.get("PROGRAMFILES", r"C:\Program Files")),
    ]
    result = []
    for root in roots:
        candidate = root / "Microsoft VS Code" / "Code.exe"
        if candidate.is_file():
            result.append({"id": "vscode", "label": "VS Code", "path": str(candidate)})
            break
    return result


def set_volume(percent: int) -> None:
    if sys.platform != "win32":
        raise RuntimeError("VOLUME_WINDOWS_ONLY")
    if type(percent) is not int or not 0 <= percent <= 100:
        raise ValueError("VOLUME_INVALID")
    from ctypes import wintypes

    class Guid(ctypes.Structure):
        _fields_ = [
            ("a", wintypes.DWORD),
            ("b", wintypes.WORD),
            ("c", wintypes.WORD),
            ("d", ctypes.c_ubyte * 8),
        ]

    def guid(value: str) -> Guid:
        return Guid.from_buffer_copy(uuid.UUID(value).bytes_le)

    ole = ctypes.WinDLL("ole32", use_last_error=True)
    ole.CoInitializeEx.argtypes = [ctypes.c_void_p, wintypes.DWORD]
    ole.CoInitializeEx.restype = ctypes.c_long
    initialized = ole.CoInitializeEx(None, 2)
    if initialized < 0 and initialized != -2147417850:
        raise RuntimeError("AUDIO_COM_INIT_FAILED")
    ole.CoCreateInstance.argtypes = [
        ctypes.POINTER(Guid),
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(Guid),
        ctypes.POINTER(ctypes.c_void_p),
    ]
    ole.CoCreateInstance.restype = ctypes.c_long
    objects: list[Any] = []

    def method(obj: Any, index: int, *types: Any) -> Any:
        pointer = ctypes.cast(obj, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents[index]
        return ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, *types)(pointer)

    try:
        clsid = guid("BCDE0395-E52F-467C-8E3D-C4579291692E")
        iid = guid("A95664D2-9614-4F35-A746-DE8DB63617E6")
        enumerator = ctypes.c_void_p()
        if (
            ole.CoCreateInstance(
                ctypes.byref(clsid), None, 23, ctypes.byref(iid), ctypes.byref(enumerator)
            )
            < 0
        ):
            raise RuntimeError("AUDIO_ENDPOINT_UNAVAILABLE")
        objects.append(enumerator)
        endpoint = ctypes.c_void_p()
        # IMMDeviceEnumerator::GetDefaultAudioEndpoint(eRender, eMultimedia).
        if (
            method(enumerator, 4, ctypes.c_int, ctypes.c_int, ctypes.POINTER(ctypes.c_void_p))(
                enumerator, 0, 1, ctypes.byref(endpoint)
            )
            < 0
        ):
            raise RuntimeError("AUDIO_ENDPOINT_UNAVAILABLE")
        objects.append(endpoint)
        volume = ctypes.c_void_p()
        iid_volume = guid("5CDF2C82-841E-4546-9722-0CF74078229A")
        if (
            method(
                endpoint,
                3,
                ctypes.POINTER(Guid),
                wintypes.DWORD,
                ctypes.c_void_p,
                ctypes.POINTER(ctypes.c_void_p),
            )(endpoint, ctypes.byref(iid_volume), 23, None, ctypes.byref(volume))
            < 0
        ):
            raise RuntimeError("AUDIO_ENDPOINT_UNAVAILABLE")
        objects.append(volume)
        if method(volume, 7, ctypes.c_float, ctypes.c_void_p)(volume, percent / 100, None) < 0:
            raise RuntimeError("VOLUME_CHANGE_FAILED")
    finally:
        for obj in reversed(objects):
            method(obj, 2)(obj)
        if initialized >= 0:
            ole.CoUninitialize()
