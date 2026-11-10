"""Wiring boundary: the only module that knows how to build agents with the app's settings/services.

Graph nodes are `@staticmethod`s, so they get their agents from here instead of a constructor.
The app calls `registry.configure(...)` once at startup (FastAPI `lifespan`); tests call
`registry.override(...)` with agents built on fake LLMs.

Agents are built lazily and cached (per language for the assistant), guarded by an asyncio.Lock
with a double check so concurrent first requests build each agent once.
"""

import asyncio
from typing import Any

from .agents import AssistantAgent, ClassifierAgent
from .llm import LLMModel, LLMSettings
from .tools import ToolSet


class AgentRegistry:
    def __init__(self) -> None:
        self._settings: LLMSettings | None = None
        self._services: dict[str, Any] = {}
        self._assistant_model = LLMModel.GPT_4_1_MINI
        self._classifier_model = LLMModel.GPT_4_1_NANO
        self._assistants: dict[str, AssistantAgent] = {}
        self._classifier: ClassifierAgent | None = None
        self._lock = asyncio.Lock()

    def configure(
        self,
        *,
        settings: LLMSettings,
        document_search: Any,
        assistant_model: LLMModel | None = None,
        classifier_model: LLMModel | None = None,
    ) -> None:
        self._settings = settings
        self._services = {"document_search": document_search}
        self._assistant_model = assistant_model or self._assistant_model
        self._classifier_model = classifier_model or self._classifier_model
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

    def _require_settings(self) -> LLMSettings:
        if self._settings is None:
            raise RuntimeError("AgentRegistry not configured: call registry.configure(...) at startup")
        return self._settings

    async def get_assistant(self, language: str) -> AssistantAgent:
        if (agent := self._assistants.get(language)) is not None:
            return agent
        async with self._lock:
            if (agent := self._assistants.get(language)) is None:
                agent = AssistantAgent(
                    self._assistant_model,
                    self._require_settings(),
                    language=language,
                    tools=ToolSet.default(**self._services),
                )
                await agent.initialize()
                self._assistants[language] = agent
        return agent

    async def get_classifier(self) -> ClassifierAgent:
        if self._classifier is not None:
            return self._classifier
        async with self._lock:
            if self._classifier is None:
                agent = ClassifierAgent(self._classifier_model, self._require_settings())
                await agent.initialize()
                self._classifier = agent
        return self._classifier


registry = AgentRegistry()
