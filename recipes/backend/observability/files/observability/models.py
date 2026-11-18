"""Data of the observability layer. Pydantic, frozen where it is a record."""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class TracingProvider(StrEnum):
    NONE = "none"
    LANGFUSE = "langfuse"
    OPIK = "opik"
    LANGSMITH = "langsmith"


class RunInfo(BaseModel):
    """Who and what a run is about. Goes to the trace as metadata/tags; the LLM never sees it."""

    model_config = ConfigDict(frozen=True)

    thread_id: str = Field(description="Server-side conversation id (with the tenant as namespace).")
    tenant_id: str
    user_id: str
    request_id: str | None = Field(default=None, description="X-Request-ID of the HTTP request, to cross logs and trace.")
    name: str = "turn"
    tags: list[str] = Field(default_factory=list)


class TokenUsage(BaseModel):
    """One LLM call, from `AIMessage.usage_metadata`."""

    model_config = ConfigDict(frozen=True)

    model: str = "unknown"
    input_tokens: int = 0
    output_tokens: int = 0
    cached_input_tokens: int = Field(default=0, description="Part of input_tokens served from the prompt cache.")

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


class ModelPrice(BaseModel):
    """USD per million tokens."""

    model_config = ConfigDict(frozen=True)

    input: float = Field(ge=0)
    output: float = Field(ge=0)
    cached_input: float | None = Field(default=None, ge=0, description="None -> same as input.")


class Prices(BaseModel):
    """`{model_name: ModelPrice}`. Keep it in the project (settings or a YAML): prices change."""

    model_config = ConfigDict(frozen=True)

    by_model: dict[str, ModelPrice] = Field(default_factory=dict)

    def cost_usd(self, usage: TokenUsage) -> float | None:
        """None when the model has no price: an unknown cost must not be reported as 0."""
        price = self.by_model.get(usage.model)
        if price is None:
            return None
        cached_price = price.input if price.cached_input is None else price.cached_input
        fresh = usage.input_tokens - usage.cached_input_tokens
        return (fresh * price.input + usage.cached_input_tokens * cached_price + usage.output_tokens * price.output) / 1e6


class TurnSummary(BaseModel):
    """What one turn cost: for the log line, the spend table or the admin page."""

    model_config = ConfigDict(frozen=True)

    thread_id: str
    tenant_id: str
    user_id: str
    request_id: str | None = None
    llm_calls: int
    input_tokens: int
    output_tokens: int
    cached_input_tokens: int
    cost_usd: float | None = Field(default=None, description="None if any call has no price.")
    duration_ms: int
    error: str | None = Field(default=None, description="Class name of the failure, never its text.")
    trace_id: str | None = Field(default=None, description="Provider trace id when it is known before flushing.")

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens
