"""Allowlisted diagnostic fields only. Do not serialize controller/settings wholesale."""

from __future__ import annotations

import io
import json
import platform
import re
import zipfile
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError, version
from typing import Any

from . import __version__

ERROR_CODES = frozenset(
    {
        "ASR_FAILED",
        "EMPTY_TRANSCRIPT",
        "ENGINE_INIT_OR_RUNTIME_FAILED",
        "MODELS_OR_KEYWORD_INVALID",
        "AUDIO_OVERFLOW_OR_DISCONNECT",
        "AUDIO_UNAVAILABLE",
        "DEVICE_DISCONNECTED",
        "DEVICE_STALLED",
        "MICROPHONE_OPEN_FAILED",
        "NO_INPUT_DEVICE",
        "DIALOGUE_OR_TTS_FAILED",
        "PROVIDER_TIMEOUT",
        "PROVIDER_DISABLED",
        "API_KEY_MISSING",
        "PROVIDER_NETWORK_OR_RESPONSE_FAILED",
        "PROVIDER_RESPONSE_INVALID",
        "PROVIDER_RESPONSE_TOO_LARGE",
        "TOOLS_UNAVAILABLE",
        "TOOL_RECURSION_REJECTED",
    }
)


def safe_report(controller: Any) -> dict[str, Any]:
    dependencies = {}
    for name in ("sherpa-onnx", "sounddevice", "numpy", "pypinyin", "soxr", "httpx"):
        try:
            dependencies[name] = version(name)
        except PackageNotFoundError:
            dependencies[name] = "MISSING"
    codes = []
    with controller.lock:
        for event in list(controller.events):
            code = event.get("code")
            if (
                event.get("type") == "error"
                and isinstance(code, str)
                and (code in ERROR_CODES or re.fullmatch(r"PROVIDER_HTTP_[1-5][0-9]{2}", code))
            ):
                codes.append(code)
        metrics = []
        for event in list(controller.metrics)[-30:]:
            item = {}
            for key in ("llm_ms", "tts_ms", "total_ms"):
                value = event.get(key)
                if type(value) in {float, int} and 0 <= value <= 600000:
                    item[key] = round(value, 1)
            outcome = event.get("outcome")
            if outcome in {"ok", "cancelled", "PROVIDER_TIMEOUT", "DIALOGUE_OR_TTS_FAILED"}:
                item["outcome"] = outcome
            metrics.append(item)
        state = (
            controller.state
            if controller.state
            in {
                "MUTED",
                "IDLE",
                "LISTENING",
                "TRANSCRIBING",
                "THINKING",
                "ACTING",
                "SPEAKING",
                "ERROR",
            }
            else "UNKNOWN"
        )
    return {
        "schema": 1,
        "app_version": __version__,
        "created_at_utc": datetime.now(UTC).isoformat(),
        "os": platform.system(),
        "architecture": platform.machine(),
        "python": platform.python_version(),
        "dependencies": dependencies,
        "state": state,
        "audio_running": controller.audio_running,
        "provider": controller.settings.provider,
        "tts": controller.settings.tts,
        "cloud_enabled": controller.settings.is_cloud,
        "error_codes": codes[-20:],
        "metrics": metrics,
        "hardware_acceptance": "NOT_VERIFIED",
        "privacy": "No audio, text, keys, URLs, user paths or device names",
    }


def diagnostic_zip(controller: Any) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "diagnostics.json", json.dumps(safe_report(controller), ensure_ascii=False, indent=2)
        )
    return output.getvalue()
