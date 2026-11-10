"""Conditional edges: pure functions of the state that return the next node's name."""

from .nodes import AGENT_NODE, REJECT_NODE
from .state import GraphState


def route_after_router(state: GraphState) -> str:
    return REJECT_NODE if state.blocked else AGENT_NODE
