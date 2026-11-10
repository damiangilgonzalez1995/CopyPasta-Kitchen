"""Concrete agents. Each one only declares what makes it different."""

from collections.abc import Sequence

from langchain.agents.middleware import AgentMiddleware
from langchain_core.tools import BaseTool

from ..middleware import build_language_middleware
from ..prompts import load_prompt
from .base_agent import BaseAgent
from .models import AgentType, Classification


class AssistantAgent(BaseAgent):
    """Conversational agent with tools. Plain-text answer (no response_format)."""

    agent_type = AgentType.ASSISTANT

    def __init__(self, *args, tools: Sequence[BaseTool], **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._tools = list(tools)

    def get_prompt(self) -> str:
        return load_prompt("assistant", self.language).render()

    def get_tools(self) -> Sequence[BaseTool]:
        return self._tools

    def get_middleware(self) -> Sequence[AgentMiddleware]:
        return [build_language_middleware()]


class ClassifierAgent(BaseAgent):
    """Single-call agent without tools that returns a structured answer."""

    agent_type = AgentType.CLASSIFIER
    response_format = Classification

    def get_prompt(self) -> str:
        return (
            "Classify the user's question. Categories: billing, technical, other.\n"
            "Set needs_search to true if the answer depends on the user's documents."
        )
