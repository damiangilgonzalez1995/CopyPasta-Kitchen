"""Wiring boundary: the only module that knows how to build agents with the app's services.

Graph nodes are `@staticmethod`s, so they get their agents from here instead of a constructor.
Models and API keys come from the project settings (`get_llm_settings()`); the app only injects
services with `registry.configure(...)` once at startup (FastAPI `lifespan`). Tests call
`registry.override(...)` with agents built on fake LLMs.

Agents are built lazily and cached (per language for the assistant), guarded by an asyncio.Lock
with a double check so concurrent first requests build each agent once.
"""

import asyncio
from typing import Any

from .agents import AssistantAgent, ClassifierAgent
from .llm import LLMModel, LLMSettings, get_llm_settings
from .tools import ToolSet


class AgentRegistry:
    def __init__(self) -> None:
        self._settings: LLMSettings | None = None
        self._services: dict[str, Any] | None = None
        self._assistants: dict[str, AssistantAgent] = {}
        self._classifier: ClassifierAgent | None = None
        self._lock = asyncio.Lock()

    def configure(
        self,
        *,
        document_search: Any,
        settings: LLMSettings | None = None,
    ) -> None:
        """`settings=None` -> `get_llm_settings()`. Pass one only in tests."""
        self._settings = settings or get_llm_settings()
        self._services = {"document_search": document_search}
        self.reset()

    def override(
        self, *, assistant: AssistantAgent | None = None, classifier: ClassifierAgent | None = None, language: str = "es"
    ) -> None:
        """Tests: inject ready-made agents."""
        if assistant is not None:
            self._assistants[language] = assistant
        if classifier is not None:
            self._classifier = classifier

    def reset(self) -> None:
        self._assistants.clear()
        self._classifier = None

    def _require_configured(self) -> tuple[LLMSettings, dict[str, Any]]:
        if self._settings is None or self._services is None:
            raise RuntimeError("AgentRegistry not configured: call registry.configure(...) at startup")
        return self._settings, self._services

    async def get_assistant(self, language: str) -> AssistantAgent:
        if (agent := self._assistants.get(language)) is not None:
            return agent
        async with self._lock:
            if (agent := self._assistants.get(language)) is None:
                settings, services = self._require_configured()
                agent = AssistantAgent(
                    LLMModel.from_id(settings.assistant_model),
                    settings,
                    language=language,
                    tools=ToolSet.default(**services),
                )
                await agent.initialize()
                self._assistants[language] = agent
        return agent

    async def get_classifier(self) -> ClassifierAgent:
        if self._classifier is not None:
            return self._classifier
        async with self._lock:
            if self._classifier is None:
                settings, _ = self._require_configured()
                agent = ClassifierAgent(LLMModel.from_id(settings.classifier_model), settings)
                await agent.initialize()
                self._classifier = agent
        return self._classifier


registry = AgentRegistry()
