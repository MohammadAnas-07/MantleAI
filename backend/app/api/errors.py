"""One error shape for the whole API (rule 27): {"error": {"code", "message", "details"}},
and the JSON-only rule for write requests (rule 29)."""

import json
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.types import ASGIApp, Receive, Scope, Send

from app.core.errors import AppError

_STATUS_CODES = {
    400: "bad_request",
    404: "not_found",
    405: "method_not_allowed",
    409: "conflict",
    415: "unsupported_media_type",
    422: "validation_error",
}


def error_body(code: str, message: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"error": {"code": code, "message": message, "details": details or {}}}


def _safe_validation_errors(exc: RequestValidationError) -> list[dict[str, Any]]:
    # Drop "input" and "ctx": they can echo what was sent, for example an API key.
    return [
        {"loc": list(e.get("loc", [])), "msg": e.get("msg", ""), "type": e.get("type", "")}
        for e in exc.errors()
    ]


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def app_error(_: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(error_body(exc.code, exc.message, exc.details), exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        details = {"errors": _safe_validation_errors(exc)}
        return JSONResponse(error_body("validation_error", "Invalid request.", details), 422)

    @app.exception_handler(StarletteHTTPException)
    async def http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = _STATUS_CODES.get(exc.status_code, "http_error")
        return JSONResponse(error_body(code, str(exc.detail)), exc.status_code)


class JsonOnlyMiddleware:
    """Reject POST/PUT/PATCH under /api without `Content-Type: application/json` (415).

    A plain HTML form can't send that header without a CORS preflight, so other websites can't
    make simple cross-site writes to the local API. Pure ASGI, so SSE streaming is unaffected.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if (
            scope["type"] == "http"
            and scope["method"] in {"POST", "PUT", "PATCH"}
            and scope["path"].startswith("/api/")
        ):
            headers = dict(scope.get("headers") or [])
            content_type = headers.get(b"content-type", b"").decode("latin-1").lower()
            if not content_type.startswith("application/json"):
                body = json.dumps(
                    error_body("unsupported_media_type", "Send JSON (application/json).")
                ).encode()
                await send(
                    {
                        "type": "http.response.start",
                        "status": 415,
                        "headers": [(b"content-type", b"application/json")],
                    }
                )
                await send({"type": "http.response.body", "body": body})
                return
        await self.app(scope, receive, send)


def _split_host(value: str) -> tuple[str, str | None]:
    """("localhost", "8000") from "localhost:8000"; IPv6 literals keep their brackets."""
    value = value.strip().lower()
    if value.startswith("["):
        end = value.find("]")
        host, rest = value[: end + 1], value[end + 1 :]
        return host, rest[1:] if rest.startswith(":") else None
    host, _, port = value.partition(":")
    return host, port or None


def host_allowed(value: str, allowed: list[str]) -> bool:
    """True when the Host header matches an allowed entry. An entry without a port matches
    that host on any port; an entry with a port matches only that port."""
    host, port = _split_host(value)
    if not host:
        return False
    for entry in allowed:
        e_host, e_port = _split_host(entry)
        if host == e_host and (e_port is None or e_port == port):
            return True
    return False


class AllowedHostsMiddleware:
    """Refuse requests whose Host header is not in ALLOWED_HOSTS (400 `invalid_host`).

    Pure ASGI, like JsonOnlyMiddleware, and it answers in the API's error shape. Starlette's
    TrustedHostMiddleware would answer in plain text.
    """

    def __init__(self, app: ASGIApp, allowed_hosts: list[str]) -> None:
        self.app = app
        self.allowed_hosts = allowed_hosts

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] in ("http", "websocket"):
            headers = dict(scope.get("headers") or [])
            host = headers.get(b"host", b"").decode("latin-1")
            if not host_allowed(host, self.allowed_hosts):
                body = json.dumps(
                    error_body(
                        "invalid_host",
                        "This host name is not allowed. Open Mantle at localhost or 127.0.0.1.",
                    )
                ).encode()
                await send(
                    {
                        "type": "http.response.start",
                        "status": 400,
                        "headers": [(b"content-type", b"application/json")],
                    }
                )
                await send({"type": "http.response.body", "body": body})
                return
        await self.app(scope, receive, send)
