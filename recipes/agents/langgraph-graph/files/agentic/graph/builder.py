"""The ONLY place with the topology. Shared by invoke and stream modes.

    START -> router_node -> (agent_node | reject_node) -> END

Compiled once per process, without a checkpointer (memory lives in `agentic/memory`).
"""

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from ..context import AgentContext
from .edges import route_after_router
from .nodes import AGENT_NODE, REJECT_NODE, ROUTER_NODE, AgentNode, RejectNode, RouterNode
from .state import GraphState

_compiled: CompiledStateGraph | None = None


def build_graph() -> StateGraph:
    builder = StateGraph(GraphState, context_schema=AgentContext)

    builder.add_node(ROUTER_NODE, RouterNode.invoke)
    builder.add_node(AGENT_NODE, AgentNode.invoke)
    builder.add_node(REJECT_NODE, RejectNode.invoke)

    builder.add_edge(START, ROUTER_NODE)
    builder.add_conditional_edges(ROUTER_NODE, route_after_router, [AGENT_NODE, REJECT_NODE])
    builder.add_edge(AGENT_NODE, END)
    builder.add_edge(REJECT_NODE, END)
    return builder


def compile_graph() -> CompiledStateGraph:
    global _compiled
    if _compiled is None:
        _compiled = build_graph().compile()
    return _compiled
