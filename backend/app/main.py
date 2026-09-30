"""App factory: middleware, error handlers, routers."""
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.config import settings
from app.logging_mw import request_logging_middleware, setup_logging
from app.routers import health

ERROR_CODES = {
    400: "bad_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
    409: "conflict",
    422: "validation_error",
    503: "service_unavailable",
}


def error_response(status_code, message, headers=None):
    code = ERROR_CODES.get(status_code, "error")
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": message}},
        headers=headers,
    )


async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    return error_response(exc.status_code, str(exc.detail), getattr(exc, "headers", None))


async def validation_exception_handler(request: Request, exc: RequestValidationError):
    # e.g. "body.episodes_requested: Input should be greater than 0"
    parts = []
    for err in exc.errors():
        location = ".".join(str(p) for p in err["loc"])
        parts.append(f"{location}: {err['msg']}")
    return error_response(422, "; ".join(parts))


def create_app():
    setup_logging(settings.log_level)

    app = FastAPI(title="Dataset Request Desk")
    app.middleware("http")(request_logging_middleware)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)

    app.include_router(health.router)
    return app


app = create_app()
