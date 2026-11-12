"""Events sent to the client over SSE. The frontend contract: change it with care."""

import json
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class EventType(str, Enum):
    TOKEN = "token"
    TOOL_START = "tool_start"
    TOOL_END = "tool_end"
    ROUTING = "routing"
    ERROR = "error"
    DONE = "done"


class SSEEvent(BaseModel):
    model_config = ConfigDict(frozen=True)

    type: EventType
    data: dict[str, Any] = Field(default_factory=dict)

    def to_sse(self) -> dict[str, str]:
        """Shape expected by `sse_starlette.EventSourceResponse`."""
        return {"event": self.type.value, "data": json.dumps(self.data, ensure_ascii=False)}

    def as_dict(self) -> dict[str, Any]:
        return {"type": self.type.value, **self.data}
