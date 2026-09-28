"""API errors with stable codes, rendered as `{code, message}` (see openapi.yaml `Error`)."""

from typing import Literal

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

ErrorCode = Literal[
    "UNAUTHENTICATED",
    "FORBIDDEN",
    "NOT_FOUND",
    "VALIDATION",
    "LINK_INVALID",
    "LINK_REVOKED",
    "LINK_EXPIRED",
    "LINK_EXHAUSTED",
    "SESSION_ENDED",
    "SESSION_ARCHIVED",
    "SESSION_FULL",
    "EDIT_LOCKED",
    "PARTICIPANT_REMOVED",
    "CONFLICT",
]

STATUS: dict[str, int] = {
    "UNAUTHENTICATED": 401,
    "FORBIDDEN": 403,
    "NOT_FOUND": 404,
    "VALIDATION": 422,
    "LINK_INVALID": 404,
    "LINK_REVOKED": 410,
    "LINK_EXPIRED": 410,
    "LINK_EXHAUSTED": 410,
    "SESSION_ENDED": 409,
    "SESSION_ARCHIVED": 410,
    "SESSION_FULL": 409,
    "EDIT_LOCKED": 403,
    "PARTICIPANT_REMOVED": 403,
    "CONFLICT": 409,
}


class ApiError(Exception):
    def __init__(self, code: ErrorCode, message: str):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = STATUS[code]


def _body(code: str, message: str) -> dict[str, str]:
    return {"code": code, "message": message}


def _validation_message(exc: RequestValidationError) -> str:
    errors = exc.errors()
    if not errors:
        return "Invalid request."
    first = errors[0]
    location = ".".join(str(p) for p in first.get("loc", ()) if p not in ("body", "query", "path"))
    message = first.get("msg", "Invalid value")
    # Custom validators already produce user-facing messages.
    if message.startswith("Value error, "):
        return message.removeprefix("Value error, ")
    return f"{location}: {message}" if location else message


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def api_error(_: Request, exc: ApiError) -> JSONResponse:
        headers = {"WWW-Authenticate": "Bearer"} if exc.status == 401 else None
        return JSONResponse(_body(exc.code, exc.message), status_code=exc.status, headers=headers)

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(_body("VALIDATION", _validation_message(exc)), status_code=422)

    @app.exception_handler(StarletteHTTPException)
    async def http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = {401: "UNAUTHENTICATED", 403: "FORBIDDEN", 404: "NOT_FOUND", 409: "CONFLICT"}.get(
            exc.status_code, "VALIDATION"
        )
        return JSONResponse(_body(code, str(exc.detail)), status_code=exc.status_code)
