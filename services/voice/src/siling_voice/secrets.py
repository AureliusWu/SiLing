"""Windows user-scoped DPAPI storage. Never return the stored key over HTTP."""

from __future__ import annotations

import ctypes
import os
import sys
from pathlib import Path

from .config import data_dir


def _crypt(data: bytes, decrypt: bool = False) -> bytes:
    if sys.platform != "win32":
        raise RuntimeError("SECURE_STORAGE_WINDOWS_ONLY")
    from ctypes import wintypes

    class Blob(ctypes.Structure):
        _fields_ = [("size", wintypes.DWORD), ("data", ctypes.POINTER(ctypes.c_byte))]

    buffer = ctypes.create_string_buffer(data)
    source = Blob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_byte)))
    output = Blob()
    library = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    function = library.CryptUnprotectData if decrypt else library.CryptProtectData
    function.argtypes = [
        ctypes.POINTER(Blob),
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(Blob),
    ]
    function.restype = wintypes.BOOL
    if not function(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(output)):
        raise RuntimeError("SECURE_STORAGE_FAILED")
    try:
        return ctypes.string_at(output.data, output.size)
    finally:
        kernel.LocalFree(output.data)


class KeyStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or data_dir() / "api-key.dpapi"

    def get(self) -> str:
        environment = os.environ.get("SILING_API_KEY", "")
        if environment:
            return environment
        if not self.path.exists():
            return ""
        return _crypt(self.path.read_bytes(), decrypt=True).decode("utf-8")

    def set(self, key: str) -> None:
        if not key or len(key) > 4096 or any(ord(c) < 33 for c in key):
            raise ValueError("API_KEY_INVALID")
        encrypted = _crypt(key.encode("utf-8"))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_bytes(encrypted)
        temporary.replace(self.path)

    def delete(self) -> None:
        self.path.unlink(missing_ok=True)

    def configured(self) -> bool:
        return bool(os.environ.get("SILING_API_KEY")) or self.path.is_file()
