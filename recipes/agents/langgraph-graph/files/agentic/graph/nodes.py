"""Graph nodes: one class per node with `@staticmethod async invoke(state, runtime) -> dict`.

- The node name is a module constant; the topology uses only the constants.
- `runtime.context` is the `AgentContext` (tenant, user, language).
- Agents come from `registry`, never built inside a node.
- A node returns only the keys it writes.
- Auxiliary nodes fail OPEN (the router falls through to the agent); security never does.
"""

import logging
from typing import Any

from langchain_core.callbacks import adispatch_custom_event
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.runtime import Runtime

from ..context import AgentContext
from ..registry import registry
from .state import GraphState

logger = logging.getLogger(__name__)

ROUTER_NODE = "router_node"
AGENT_NODE = "agent_node"
REJECT_NODE = "reject_node"

ALLOWED_CATEGORIES = {"billing", "technical"}

REJECT_TEXT = {
    "es": "Solo puedo ayudarte con temas de facturación o soporte técnico.",
    "en": "I can only help with billing or technical support.",
}


class RouterNode:
    @staticmethod
    async def invoke(state: GraphState, runtime: Runtime[AgentContext]) -> dict[str, Any]:
        try:
            classifier = await registry.get_classifier()
            turn = await classifier.process(state.question, context=runtime.context, history=state.history)
            classification = turn.structured
        except Exception:
            logger.exception("Router failed; letting the question through")
            return {"classification": None, "blocked": False}

        blocked = classification.category not in ALLOWED_CATEGORIES
        await adispatch_custom_event("routing", {"category": classification.category, "blocked": blocked})
        return {"classification": classification, "blocked": blocked}


class AgentNode:
    @staticmethod
    async def invoke(state: GraphState, runtime: Runtime[AgentContext]) -> dict[str, Any]:
        agent = await registry.get_assistant(runtime.context.language)
        turn = await agent.process(state.question, context=runtime.context, history=state.history)
        return {"answer": turn.answer, "new_messages": turn.new_messages}


class RejectNode:
    @staticmethod
    async def invoke(state: GraphState, runtime: Runtime[AgentContext]) -> dict[str, Any]:
        text = REJECT_TEXT.get(runtime.context.language, REJECT_TEXT["es"])
        return {"answer": text, "new_messages": [HumanMessage(state.question), AIMessage(text)]}
