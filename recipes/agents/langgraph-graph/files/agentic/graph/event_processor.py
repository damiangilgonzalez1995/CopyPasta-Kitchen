"""Translate raw `astream_events(version="v2")` events into `SSEEvent`s. Pure: no I/O.

- Tokens: only from the chat model of the answering agent (`AGENT_NODE`), so the router's
  structured output never leaks to the user.
- Tools: start/end with the tool name only (no args/outputs: they may hold private data).
- Custom events (`adispatch_custom_event`) pass through by name.
- The final state is the output of the root run (`on_chain_end` without parents).
"""

from typing import Any

from .events import EventType, SSEEvent
from .nodes import AGENT_NODE
from .state import GraphState


class EventProcessor:
    def __init__(self) -> None:
        self.final_state: GraphState | None = None

    def process(self, raw: dict[str, Any]) -> list[SSEEvent]:
        kind = raw.get("event")
        metadata = raw.get("metadata") or {}
        in_agent = str(metadata.get("checkpoint_ns", "")).startswith(AGENT_NODE) or (
            metadata.get("langgraph_node") == AGENT_NODE
        )

        if kind == "on_chat_model_stream" and in_agent:
            text = getattr(raw["data"].get("chunk"), "text", "")
            text = str(text) if text else ""
            return [SSEEvent(EventType.TOKEN, {"text": text})] if text else []

        if kind == "on_tool_start":
            return [SSEEvent(EventType.TOOL_START, {"tool": raw.get("name")})]

        if kind == "on_tool_end":
            return [SSEEvent(EventType.TOOL_END, {"tool": raw.get("name")})]

        if kind == "on_custom_event":
            if raw.get("name") == EventType.ROUTING.value:
                return [SSEEvent(EventType.ROUTING, dict(raw.get("data") or {}))]
            return []

        if kind == "on_chain_end" and not raw.get("parent_ids"):
            output = raw["data"].get("output")
            if output is not None:
                self.final_state = output if isinstance(output, GraphState) else GraphState.model_validate(output)
        return []
