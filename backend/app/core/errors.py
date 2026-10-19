"""One error format for the whole API: {"error": {"code": "...", "message": "..."}}."""

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)

# Machine-readable codes for the common built-in HTTP errors.
STATUS_CODES = {
    400: "bad_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
    409: "conflict",
    429: "rate_limited",
}


def error_body(code: str, message: str) -> dict:
    return {"error": {"code": code, "message": message}}


class AppError(Exception):
    """Raise this anywhere in our code to return a clean error to the client."""

    def __init__(self, status_code: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message


async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content=error_body(exc.code, exc.message))


async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    # Covers 404 (unknown URL), 405, and any HTTPException raised by FastAPI itself.
    code = STATUS_CODES.get(exc.status_code, "http_error")
    return JSONResponse(
        status_code=exc.status_code,
        content=error_body(code, str(exc.detail)),
        headers=exc.headers,
    )


def format_validation_error(exc: RequestValidationError) -> str:
    parts = []
    for err in exc.errors():
        # loc looks like ("body", "email"); drop the first part to keep the message short.
        field = ".".join(str(p) for p in err["loc"][1:]) or "request"
        parts.append(f"{field}: {err['msg']}")
    return "; ".join(parts)


async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content=error_body("validation_error", format_validation_error(exc)),
    )


async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    # Log the details for us, but never show them to the client.
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content=error_body("internal_error", "Something went wrong on our side."),
    )


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, app_error_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(Exception, unhandled_error_handler)
