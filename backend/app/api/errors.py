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
