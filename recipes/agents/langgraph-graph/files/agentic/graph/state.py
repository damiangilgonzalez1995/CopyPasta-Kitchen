"""Graph state: the data contract between nodes.

Pydantic, with a description per field. Nodes return a dict with ONLY the keys they write.
Add a reducer (`Annotated[list[X], operator.add]`) only to keys that several nodes write in
the same step (parallel branches); everything else is last-write-wins.

Security data (tenant, user) does NOT live here: it is in `AgentContext` (`runtime.context`).
"""

from langchain_core.messages import BaseMessage
from pydantic import BaseModel, ConfigDict, Field

from ..agents import Classification


class GraphState(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    # Input
    question: str = Field(description="The user's question for this turn.")
    history: list[BaseMessage] = Field(default_factory=list, description="Previous turns read from memory.")

    # Written by router_node
    classification: Classification | None = Field(default=None, description="Router verdict; None if it failed.")
    blocked: bool = Field(default=False, description="True if the question is out of scope.")

    # Written by agent_node / reject_node
    answer: str | None = Field(default=None, description="Final answer shown to the user.")
    new_messages: list[BaseMessage] = Field(
        default_factory=list, description="Messages produced this turn, to persist in memory."
    )
