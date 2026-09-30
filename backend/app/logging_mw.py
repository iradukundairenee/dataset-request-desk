"""Structured JSON logging: one line per request."""
import json
import logging
import time
import traceback
import uuid
from datetime import datetime, timezone

from fastapi import Request
from fastapi.responses import JSONResponse

logger = logging.getLogger("app.request")


def setup_logging(level):
    # Every log line is already a JSON string, so the format is just the message.
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.handlers = [handler]
    logger.setLevel(level)
    logger.propagate = False


def log_json(level, **fields):
    fields = {"ts": datetime.now(timezone.utc).isoformat(), **fields}
    logger.log(level, json.dumps(fields, default=str))


async def request_logging_middleware(request: Request, call_next):
    request_id = uuid.uuid4().hex
    request.state.request_id = request_id
    start = time.perf_counter()

    try:
        response = await call_next(request)
    except Exception:
        # Unhandled error: log the traceback server-side, return a generic 500
        # to the client so no internals leak.
        log_json(
            logging.ERROR,
            event="unhandled_error",
            request_id=request_id,
            traceback=traceback.format_exc(),
        )
        response = JSONResponse(
            status_code=500,
            content={"error": {"code": "internal_error", "message": "Internal server error"}},
        )

    duration_ms = round((time.perf_counter() - start) * 1000, 2)
    response.headers["X-Request-ID"] = request_id
    log_json(
        logging.INFO,
        event="request",
        request_id=request_id,
        method=request.method,
        path=request.url.path,  # path only: query strings are not logged
        status=response.status_code,
        duration_ms=duration_ms,
        # Set by the auth dependency (phase 3) once the user is known.
        user_id=getattr(request.state, "user_id", None),
    )
    return response
