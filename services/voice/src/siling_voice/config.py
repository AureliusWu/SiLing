from __future__ import annotations

import json
import os
import re
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def data_dir() -> Path:
    root = os.environ.get("SILING_CONFIG_DIR")
    if root:
        return Path(root).expanduser()
    return Path(os.environ.get("LOCALAPPDATA", Path.home() / ".cache")) / "SiLing"


def model_dir() -> Path:
    return Path(os.environ.get("SILING_MODEL_DIR", str(data_dir() / "models"))).expanduser()


class Settings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    wake_word: str = "你好司聆"
    device: int | None = Field(default=None, ge=0)
    silence_ms: int = Field(default=700, ge=250, le=2500)
    speech_wait_ms: int = Field(default=6000, ge=1000, le=15000)
    max_record_ms: int = Field(default=15000, ge=2000, le=30000)
    min_speech_ms: int = Field(default=200, ge=64, le=1000)
    cooldown_ms: int = Field(default=900, ge=300, le=5000)
    kws_threshold: float = Field(default=0.25, ge=0.05, le=0.9)
    num_threads: int = Field(default=2, ge=1, le=8)
    chime: bool = True

    @field_validator("wake_word")
    @classmethod
    def chinese_keyword(cls, value: str) -> str:
        if not re.fullmatch(r"[\u4e00-\u9fff]{2,12}", value):
            raise ValueError("唤醒词需为 2–12 个汉字；R1 暂不支持混合英文或标点")
        return value

    @model_validator(mode="after")
    def timing_order(self) -> Settings:
        if self.speech_wait_ms >= self.max_record_ms:
            raise ValueError("等待开口时限必须小于最长录音时限")
        if self.min_speech_ms >= self.max_record_ms:
            raise ValueError("最短语音时长必须小于最长录音时限")
        return self


def load_settings(path: Path | None = None) -> Settings:
    target = path or data_dir() / "settings.json"
    if not target.is_file():
        return Settings()
    return Settings.model_validate_json(target.read_text(encoding="utf-8"))


def save_settings(settings: Settings, path: Path | None = None) -> None:
    target = path or data_dir() / "settings.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(".tmp")
    temporary.write_text(json.dumps(settings.model_dump(), ensure_ascii=False, indent=2), "utf-8")
    temporary.replace(target)
