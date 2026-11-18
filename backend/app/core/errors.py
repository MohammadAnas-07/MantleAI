"""Application errors. The API turns every AppError into
`{"error": {"code", "message", "details"}}` with the error's HTTP status."""

from typing import Any


class AppError(Exception):
    status_code: int = 400
    code: str = "bad_request"

    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        status_code: int | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        if code is not None:
            self.code = code
        if status_code is not None:
            self.status_code = status_code
        self.details: dict[str, Any] = details or {}


class NotFound(AppError):
    status_code = 404
    code = "not_found"
