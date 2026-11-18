"""LangSmith through an explicit `LangChainTracer` (one `Client` per process), instead of the
`LANGSMITH_TRACING` env vars: nothing traces by accident, and tests never reach the cloud.
`metadata` and `tags` of the run config land on the trace."""

from typing import Any

from .models import RunInfo
from .tracer import Tracer


class LangSmithTracer(Tracer):
    def __init__(self, client: Any, *, project_name: str, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._client = client
        self.project_name = project_name

    def _callbacks(self, run: RunInfo) -> list[Any]:
        from langchain_core.tracers.langchain import LangChainTracer

        return [LangChainTracer(project_name=self.project_name, client=self._client)]

    def _flush(self) -> None:
        self._client.flush()
