"""A closed tool vocabulary. Model output can select IDs, never paths or code."""

from __future__ import annotations

import json
import os
import platform
import re
import secrets
import subprocess
import sys
import threading
import time
import unicodedata
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator

from .config import data_dir
from .providers import Cancelled


class Target(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    id: str = Field(pattern=r"^[a-z][a-z0-9_-]{0,31}$")
    label: str = Field(min_length=1, max_length=40)
    path: str = Field(min_length=1, max_length=1024)

    @field_validator("label", "path")
    @classmethod
    def no_controls(cls, value: str) -> str:
        if any(ord(c) < 32 for c in value):
            raise ValueError("TARGET_INVALID")
        return value


class ToolConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    apps: list[Target] = Field(default_factory=list, max_length=16)
    folders: list[Target] = Field(default_factory=list, max_length=16)

    @field_validator("apps", "folders")
    @classmethod
    def unique(cls, targets: list[Target]) -> list[Target]:
        if len({target.id for target in targets}) != len(targets):
            raise ValueError("DUPLICATE_TARGET_ID")
        return targets


class AppArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    app_id: str = Field(pattern=r"^[a-z][a-z0-9_-]{0,31}$")


class FolderArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    folder_id: str = Field(pattern=r"^[a-z][a-z0-9_-]{0,31}$")


class VolumeArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    percent: StrictInt = Field(ge=0, le=100)


class EmptyArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")


ARGUMENTS: dict[str, type[BaseModel]] = {
    "open_app": AppArgs,
    "open_configured_folder": FolderArgs,
    "set_volume": VolumeArgs,
    "get_system_info": EmptyArgs,
}
BLOCKED = {
    "cmd",
    "powershell",
    "pwsh",
    "bash",
    "sh",
    "wsl",
    "wscript",
    "cscript",
    "mshta",
    "rundll32",
    "regsvr32",
    "python",
    "pythonw",
    "node",
    "reg",
    "schtasks",
    "msiexec",
    "wmic",
    "ssh",
    "curl",
    "certutil",
    "conhost",
}


def validate_target(target: Target, kind: Literal["app", "folder"]) -> Path:
    path = Path(target.path).expanduser()
    if not path.is_absolute():
        raise ValueError("TARGET_MUST_BE_ABSOLUTE")
    resolved = path.resolve(strict=True)
    # No network shares, scripts, runtime interpreters or model-controlled args.
    if str(path).startswith(("\\\\", "//")):
        raise ValueError("NETWORK_TARGET_REJECTED")
    if kind == "folder":
        if not resolved.is_dir():
            raise ValueError("FOLDER_NOT_FOUND")
    else:
        stem = resolved.stem.casefold()
        if (
            not resolved.is_file()
            or resolved.suffix.casefold() != ".exe"
            or stem in BLOCKED
            or re.fullmatch(r"python\d+(?:\.\d+)*w?", stem)
        ):
            raise ValueError("EXECUTABLE_NOT_ALLOWED")
    return resolved


def system_info() -> dict[str, Any]:
    return {
        "os": platform.system(),
        "release": platform.release(),
        "architecture": platform.machine(),
        "cpu_count": os.cpu_count(),
    }


def execute(name: str, arguments: dict[str, Any], target: Path | None) -> dict[str, Any]:
    if name == "get_system_info":
        return {"ok": True, "info": system_info()}
    if sys.platform != "win32":
        raise RuntimeError("TOOL_WINDOWS_ONLY")
    if name == "open_app":
        assert target is not None
        subprocess.Popen(
            [str(target)],
            shell=False,
            cwd=str(target.parent),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    elif name == "open_configured_folder":
        assert target is not None
        os.startfile(str(target))
    elif name == "set_volume":
        from .windows import set_volume

        set_volume(arguments["percent"])
    return {"ok": True}


@dataclass
class Pending:
    name: str
    arguments: dict[str, Any]
    label: str
    expires: float
    event: threading.Event = field(default_factory=threading.Event)
    result: dict[str, Any] | None = None


class ToolService:
    def __init__(
        self,
        policy: str = "ask",
        config: ToolConfig | None = None,
        executor: Callable[..., dict[str, Any]] = execute,
    ) -> None:
        self.policy = policy
        self.executor = executor
        self.lock = threading.RLock()
        self.pending: dict[str, Pending] = {}
        self.audit: deque[dict[str, Any]] = deque(maxlen=100)
        if config is None:
            try:
                config = ToolConfig.model_validate_json(
                    (data_dir() / "tools.json").read_text("utf-8")
                )
            except (OSError, ValueError):
                config = ToolConfig()
        self.config = config

    def update(self, config: ToolConfig) -> None:
        for target in config.apps:
            validate_target(target, "app")
        for target in config.folders:
            validate_target(target, "folder")
        self.cancel_all()
        path = data_dir() / "tools.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.with_suffix(".tmp").write_text(config.model_dump_json(indent=2), "utf-8")
        path.with_suffix(".tmp").replace(path)
        self.config = config

    def schemas(self) -> list[dict[str, Any]]:
        if self.policy == "off":
            return []
        available = {
            "get_system_info": "读取系统类型、架构和 CPU 核数，不读取文件或个人安排",
            "set_volume": "设置系统音量百分比，需要权限确认",
        }
        if self.config.apps:
            available["open_app"] = "打开已配置的应用 ID：" + ",".join(
                t.id for t in self.config.apps
            )
        if self.config.folders:
            available["open_configured_folder"] = "打开已配置的目录 ID：" + ",".join(
                t.id for t in self.config.folders
            )
        return [
            {
                "type": "function",
                "function": {
                    "name": name,
                    "description": description,
                    "parameters": ARGUMENTS[name].model_json_schema(),
                },
            }
            for name, description in available.items()
        ]

    def match(self, text: str) -> dict[str, Any] | None:
        if self.policy == "off":
            return None
        normalized = re.sub(r"[\s。！？!?，,]", "", unicodedata.normalize("NFKC", text)).casefold()
        name = ""
        args: dict[str, Any] = {}
        if normalized in {"查看系统信息", "获取系统信息", "系统信息"}:
            name = "get_system_info"
        volume = re.fullmatch(
            r"(?:把)?音量(?:设为|设置为|调到)(?:百分之)?(\d{1,3})(?:%)?", normalized
        )
        if volume:
            name, args = "set_volume", {"percent": int(volume[1])}
        for kind, targets in (("app", self.config.apps), ("folder", self.config.folders)):
            for target in targets:
                aliases = {target.id, re.sub(r"\s", "", target.label).casefold()}
                if any(normalized == "打开" + alias for alias in aliases):
                    name = "open_app" if kind == "app" else "open_configured_folder"
                    args = {"app_id" if kind == "app" else "folder_id": target.id}
        return (
            {
                "id": secrets.token_urlsafe(12),
                "type": "function",
                "function": {"name": name, "arguments": json.dumps(args)},
            }
            if name
            else None
        )

    def _validate(
        self, name: str, arguments: dict[str, Any]
    ) -> tuple[dict[str, Any], Path | None, str]:
        if self.policy == "off" or name not in ARGUMENTS:
            raise ValueError("TOOL_NOT_ALLOWED")
        args = ARGUMENTS[name].model_validate(arguments).model_dump()
        target, label = None, name
        if name in {"open_app", "open_configured_folder"}:
            app = name == "open_app"
            selected = next(
                (
                    t
                    for t in (self.config.apps if app else self.config.folders)
                    if t.id == args["app_id" if app else "folder_id"]
                ),
                None,
            )
            if selected is None:
                raise ValueError("TARGET_NOT_CONFIGURED")
            target = validate_target(selected, "app" if app else "folder")
            label = selected.label
        elif name == "set_volume":
            label = f"系统音量 {args['percent']}%"
        else:
            label = "读取系统信息"
        return args, target, label

    def _execute(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        started = time.perf_counter()
        try:
            args, target, _ = self._validate(name, arguments)  # revalidate at execution, too
            result = self.executor(name, args, target)
        except Exception:
            result = {"ok": False, "code": "TOOL_EXECUTION_REJECTED_OR_FAILED"}
        entry = {
            "at": time.time(),
            "tool": name,
            "ok": bool(result.get("ok")),
            "elapsed_ms": round((time.perf_counter() - started) * 1000, 1),
        }
        with self.lock:
            self.audit.append(entry)
            path = data_dir() / "tool-audit.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.with_suffix(".tmp").write_text(json.dumps(list(self.audit)), "utf-8")
            path.with_suffix(".tmp").replace(path)
        return result

    def request(
        self, call: dict[str, Any], cancel: threading.Event, emit: Callable[[dict[str, Any]], None]
    ) -> dict[str, Any]:
        try:
            name = call["function"]["name"]
            raw = call["function"]["arguments"]
            if not isinstance(raw, str) or len(raw) > 2048:
                raise ValueError()
            arguments = json.loads(raw)
            args, _, label = self._validate(name, arguments)
        except Exception:
            return {"ok": False, "code": "TOOL_ARGUMENTS_REJECTED"}
        if cancel.is_set():
            raise Cancelled()
        if name == "get_system_info" or self.policy == "trusted":
            result = self._execute(name, args)
            emit(
                {"type": "tool_result", "tool": name, "ok": result.get("ok", False), "label": label}
            )
            return result
        ticket = secrets.token_urlsafe(24)
        pending = Pending(name, args, label, time.monotonic() + 60)
        with self.lock:
            self.pending[ticket] = pending
        emit(
            {
                "type": "tool_pending",
                "ticket": ticket,
                "tool": name,
                "label": label,
                "arguments": args,
                "timeout_s": 60,
            }
        )
        while not pending.event.wait(0.05):
            if cancel.is_set():
                with self.lock:
                    self.pending.pop(ticket, None)
                raise Cancelled()
            if time.monotonic() >= pending.expires:
                with self.lock:
                    self.pending.pop(ticket, None)
                return {"ok": False, "code": "TOOL_CONFIRMATION_TIMEOUT"}
        return pending.result or {"ok": False, "code": "TOOL_CANCELLED"}

    def confirm(self, ticket: str, approved: bool) -> dict[str, Any]:
        with self.lock:
            pending = self.pending.pop(ticket, None)
            if pending is None or time.monotonic() >= pending.expires:
                raise ValueError("TOOL_TICKET_EXPIRED")
            pending.result = (
                self._execute(pending.name, pending.arguments)
                if approved
                else {"ok": False, "code": "TOOL_REJECTED_BY_USER"}
            )
            pending.event.set()
            return pending.result

    def cancel_all(self) -> None:
        with self.lock:
            for pending in self.pending.values():
                pending.result = {"ok": False, "code": "TOOL_CANCELLED"}
                pending.event.set()
            self.pending.clear()

    def snapshot(self) -> dict[str, Any]:
        with self.lock:
            return {
                "config": self.config.model_dump(),
                "policy": self.policy,
                "pending": [
                    {"ticket": ticket, "tool": p.name, "label": p.label, "arguments": p.arguments}
                    for ticket, p in self.pending.items()
                ],
                "audit": list(self.audit),
            }
