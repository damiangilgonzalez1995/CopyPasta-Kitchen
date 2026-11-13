"""One error shape for the whole API, inside FastAPI's own `{"detail": ...}` envelope:

    {"detail": {"code": "<machine_readable>", ...extra fields}}

`code` is what clients branch on (`rate_limited`, `ai_quota_daily_exhausted`...); the extra fields
are whatever that code needs (`resets_at`, `retry_after`). Plain `HTTPException(404, "Not Found")`
still works (its detail is a string) for errors nobody branches on. Unexpected failures become
`{"detail": {"code": "internal_error", "request_id": ...}}` (see `request_id.py`): the internals go
to the log, the id to the client, so support can match the two.
"""

from typing import Any

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict


class ErrorDetail(BaseModel):
    """What `detail` looks like when a client should branch on it. For OpenAPI and for tests."""

    model_config = ConfigDict(frozen=True, extra="allow")

    code: str


class ApiError(HTTPException):
    """`raise ApiError(409, "conversation_locked", resets_at=...)` -> 409 {"detail": {"code": ..., "resets_at": ...}}"""

    def __init__(self, status_code: int, code: str, *, headers: dict[str, str] | None = None, **extra: Any) -> None:
        super().__init__(status_code, {"code": code, **extra}, headers)
        self.code = code
