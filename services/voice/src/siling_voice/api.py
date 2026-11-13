from __future__ import annotations

import hmac
import secrets
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, SecretStr

from . import __version__
from .audio import AudioFailure
from .config import Settings
from .controller import Controller


class Action(BaseModel):
    action: str


class Message(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(min_length=1, max_length=2000)


class Credential(BaseModel):
    model_config = ConfigDict(extra="forbid")
    key: SecretStr = Field(min_length=1, max_length=4096)


def create_app(controller: Controller, token: str | None = None) -> FastAPI:
    session_token = token or secrets.token_urlsafe(32)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        yield
        controller.mute(timeout=3)

    app = FastAPI(
        title="SiLing Local Voice",
        version=__version__,
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.state.token = session_token

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, error: RequestValidationError) -> JSONResponse:
        # FastAPI normally echoes invalid input values; never reflect credentials.
        if request.url.path.startswith("/api/credential"):
            return JSONResponse({"detail": "API_KEY_INVALID"}, status_code=422)
        return JSONResponse({"detail": "SETTINGS_OR_INPUT_INVALID"}, status_code=422)

    app.add_middleware(
        TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "testserver"]
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:1420",
            "http://127.0.0.1:1420",
            "tauri://localhost",
            "http://tauri.localhost",
        ],
        allow_methods=["GET", "POST", "PUT"],
        allow_headers=["Authorization", "Content-Type"],
    )

    @app.middleware("http")
    async def privacy_headers(request: Request, call_next):  # type: ignore[no-untyped-def]
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
            "connect-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'none'"
        )
        return response

    def authorize(authorization: Annotated[str | None, Header()] = None) -> None:
        if not hmac.compare_digest(authorization or "", f"Bearer {session_token}"):
            raise HTTPException(status_code=401, detail="UNAUTHORIZED")

    secured = [Depends(authorize)]

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"service": "SiLing", "version": __version__}

    @app.get("/api/status", dependencies=secured)
    def status(after: int = 0) -> dict:
        return controller.snapshot(after)

    @app.get("/api/devices", dependencies=secured)
    def device_list() -> dict:
        try:
            return {"devices": controller.list_devices()}
        except AudioFailure as error:
            raise HTTPException(status_code=503, detail=error.code) from error

    @app.post("/api/control", dependencies=secured)
    def control(body: Action) -> dict[str, bool]:
        try:
            if body.action == "start":
                controller.start()
            elif body.action == "mute":
                controller.mute()
            elif body.action == "clear":
                controller.clear()
            elif body.action == "exit":
                controller.mute()
                if hasattr(app.state, "shutdown"):
                    app.state.shutdown()
            elif body.action in {"wake", "cancel", "ptt_start", "ptt_stop"}:
                controller.command(body.action)
            else:
                raise HTTPException(400, "UNKNOWN_ACTION")
        except RuntimeError as error:
            raise HTTPException(409, str(error)) from error
        return {"ok": True}

    @app.post("/api/chat", dependencies=secured)
    def chat(body: Message) -> dict:
        try:
            controller.chat(body.text)
        except (ValueError, RuntimeError) as error:
            raise HTTPException(409, str(error)) from error
        return {"ok": True}

    @app.post("/api/credential", dependencies=secured)
    def credential(body: Credential) -> dict:
        try:
            controller.keys.set(body.key.get_secret_value())
        except (RuntimeError, ValueError) as error:
            raise HTTPException(400, str(error)) from error
        return {"configured": True}

    @app.post("/api/credential/delete", dependencies=secured)
    def delete_credential() -> dict:
        controller.keys.delete()
        return {"configured": controller.keys.configured()}

    @app.put("/api/settings", dependencies=secured)
    def settings(body: Settings) -> dict:
        try:
            controller.update(body)
        except RuntimeError as error:
            raise HTTPException(409, str(error)) from error
        except ValueError as error:
            raise HTTPException(400, "KEYWORD_UNSUPPORTED") from error
        return body.model_dump()

    web = Path(__file__).with_name("web")
    if web.is_dir():
        app.mount("/", StaticFiles(directory=web, html=True), name="ui")
    return app
