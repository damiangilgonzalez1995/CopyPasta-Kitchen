"""Events sent to the client over SSE. The frontend contract: change it with care."""

import json
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class EventType(str, Enum):
    TOKEN = "token"
    TOOL_START = "tool_start"
    TOOL_END = "tool_end"
    ROUTING = "routing"
    ERROR = "error"
    DONE = "done"


@dataclass(frozen=True)
class SSEEvent:
    type: EventType
    data: dict[str, Any] = field(default_factory=dict)

    def to_sse(self) -> dict[str, str]:
        """Shape expected by `sse_starlette.EventSourceResponse`."""
        return {"event": self.type.value, "data": json.dumps(self.data, ensure_ascii=False)}

    def as_dict(self) -> dict[str, Any]:
        return {"type": self.type.value, **asdict(self)["data"]}
