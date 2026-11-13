"""Every request gets an id, every response and every log line carry it, and nothing leaks on a crash.

- `X-Request-ID` from the client is kept (the frontend can generate one and trace end to end);
  otherwise a short uuid4. Only `[A-Za-z0-9._-]{1,64}`: anything else is replaced, not trusted.
- The id lives in `request.state.request_id` and in a contextvar, so `logging` records get it
  through `RequestIdFilter` without passing it around.
- An unhandled exception becomes 500 `{"detail": {"code": "internal_error", "request_id": ...}}`
  and a `logger.exception` with the same id. The client never sees the traceback.
"""

import logging
import re
import uuid
from collections.abc import Awaitable, Callable
from contextvars import ContextVar

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse

HEADER = "X-Request-ID"
VALID_ID = re.compile(r"^[A-Za-z0-9._-]{1,64}$")

request_id_var: ContextVar[str] = ContextVar("request_id", default="-")
logger = logging.getLogger(__name__)


def new_request_id() -> str:
    return uuid.uuid4().hex[:16]


def current_request_id() -> str:
    """The id of the request being handled, or "-" outside one (startup, workers)."""
    return request_id_var.get()


class RequestIdFilter(logging.Filter):
    """Adds `record.request_id` so a format can print `%(request_id)s`. See `logging_setup.py`."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get()
        return True


async def request_id_middleware(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
    incoming = request.headers.get(HEADER, "")
    request_id = incoming if VALID_ID.match(incoming) else new_request_id()
    request.state.request_id = request_id
    token = request_id_var.set(request_id)
    try:
        try:
            response = await call_next(request)
        except Exception:
            logger.exception("Unhandled error on %s %s", request.method, request.url.path)
            response = JSONResponse({"detail": {"code": "internal_error", "request_id": request_id}}, status_code=500)
        response.headers[HEADER] = request_id
        return response
    finally:
        request_id_var.reset(token)


def install_request_id(app: FastAPI) -> None:
    app.middleware("http")(request_id_middleware)
