"""Agent types, the turn result and the structured answers (`response_format`)."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from langchain_core.messages import BaseMessage
from pydantic import BaseModel, Field


class AgentType(str, Enum):
    ASSISTANT = "assistant"
    CLASSIFIER = "classifier"


@dataclass(frozen=True)
class AgentTurn:
    """What `BaseAgent.process` returns.

    - `answer`: text of the last AI message ("" if the agent only returned structured output).
    - `structured`: the `response_format` instance, or None when the agent has no response_format.
    - `new_messages`: messages produced in this turn (human + AI + tools), ready to persist in memory.
    """

    answer: str
    structured: Any = None
    new_messages: list[BaseMessage] = field(default_factory=list)


class AgentError(RuntimeError):
    """The agent ended in a state the caller cannot use. `kind` is safe to log; the text may not be."""

    def __init__(self, message: str, *, kind: str) -> None:
        super().__init__(message)
        self.kind = kind


# --- Structured answers: one Pydantic model per agent that needs one ---------------------------


class Classification(BaseModel):
    """Example `response_format` for a classifier agent."""

    category: str = Field(description="One of the categories listed in the prompt.")
    needs_search: bool = Field(description="True if answering requires searching the documents.")
    confidence: float = Field(ge=0, le=1, description="How sure the classification is, 0 to 1.")
