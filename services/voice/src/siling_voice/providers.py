"""Bounded OpenAI-compatible HTTP transport with real cancellation."""

from __future__ import annotations

import asyncio
import json
import threading
import time
from contextlib import suppress
from dataclasses import dataclass, field
from typing import Any

import httpx

from .config import Settings
from .secrets import KeyStore


class Cancelled(Exception):
    pass


class ProviderFailure(Exception):
    pass


@dataclass
class Reply:
    text: str
    calls: list[dict[str, Any]] = field(default_factory=list)


class Provider:
    def __init__(
        self,
        settings: Settings,
        keys: KeyStore | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.settings = settings
        self.keys = keys or KeyStore()
        self.transport = transport

    def complete(
        self,
        messages: list[dict[str, Any]],
        cancel: threading.Event,
        tools: list[dict[str, Any]] | None = None,
    ) -> Reply:
        if cancel.is_set():
            raise Cancelled()
        if self.settings.provider == "mock":
            count = sum(message["role"] == "user" for message in messages)
            return Reply(f"这是第{count}轮模拟回复。真实 AI 服务尚未调用。")
        if self.settings.provider not in {"ollama", "compatible"}:
            raise ProviderFailure("PROVIDER_DISABLED")
        try:
            return asyncio.run(self._request(messages, cancel, tools))
        except (Cancelled, ProviderFailure):
            raise
        except httpx.TimeoutException:
            raise ProviderFailure("PROVIDER_TIMEOUT") from None
        except Exception:
            raise ProviderFailure("PROVIDER_NETWORK_OR_RESPONSE_FAILED") from None

    async def _request(
        self,
        messages: list[dict[str, Any]],
        cancel: threading.Event,
        tools: list[dict[str, Any]] | None,
    ) -> Reply:
        headers = {"Content-Type": "application/json"}
        if self.settings.provider == "compatible":
            key = self.keys.get()
            if self.settings.is_cloud and not key:
                raise ProviderFailure("API_KEY_MISSING")
            if key:
                headers["Authorization"] = f"Bearer {key}"
        body: dict[str, Any] = {
            "model": self.settings.llm_model,
            "messages": messages,
            "stream": False,
            "max_tokens": 512,
        }
        if tools:
            body.update(tools=tools, tool_choice="auto")

        async def operation() -> Reply:
            async with (
                httpx.AsyncClient(
                    transport=self.transport,
                    trust_env=False,
                    follow_redirects=False,
                    timeout=httpx.Timeout(self.settings.request_timeout_s, connect=5),
                ) as client,
                client.stream(
                    "POST", self.settings.api_base + "/chat/completions", headers=headers, json=body
                ) as response,
            ):
                if response.status_code != 200:
                    raise ProviderFailure(f"PROVIDER_HTTP_{response.status_code}")
                raw = bytearray()
                async for chunk in response.aiter_bytes():
                    raw.extend(chunk)
                    if len(raw) > 1_048_576:
                        raise ProviderFailure("PROVIDER_RESPONSE_TOO_LARGE")
                try:
                    message = json.loads(raw)["choices"][0]["message"]
                    text = message.get("content") or ""
                    calls = message.get("tool_calls") or []
                    if not isinstance(text, str) or not isinstance(calls, list):
                        raise ValueError()
                    if len(calls) > 1 or len(text) > 12000:
                        raise ValueError()
                    if not text.strip() and not calls:
                        raise ValueError()
                    return Reply(text[:2000], calls)
                except (ValueError, KeyError, IndexError, TypeError):
                    raise ProviderFailure("PROVIDER_RESPONSE_INVALID") from None

        task = asyncio.create_task(operation())
        deadline = time.monotonic() + self.settings.request_timeout_s
        try:
            while not task.done():
                if cancel.is_set():
                    raise Cancelled()
                if time.monotonic() >= deadline:
                    raise ProviderFailure("PROVIDER_TIMEOUT")
                await asyncio.wait({task}, timeout=0.05)
            if cancel.is_set():
                raise Cancelled()
            return await task
        finally:
            if not task.done():
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task
