"""Run context: data the agent's tools and middleware need but the LLM never sees."""

from pydantic import BaseModel, ConfigDict, Field


class AgentContext(BaseModel):
    """Passed as `context=` on every run and declared as `context_schema` in `create_agent`.

    Tools read it via `runtime.context` (`ToolRuntime`), middleware via `request.runtime.context`
    and graph nodes via `runtime.context` (`Runtime`). It never goes into a prompt or a tool
    argument, so the LLM cannot read or forge the tenant.

    Add the fields your app needs (feature flags, permissions, model tier...). Keep it small
    and immutable: it is security data, not working state.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    tenant_id: str = Field(description="Tenant the run belongs to. Every data access filters by it.")
    user_id: str = Field(description="User who asked.")
    language: str = Field(default="es", description="ISO 639-1 code the answer must be written in.")
