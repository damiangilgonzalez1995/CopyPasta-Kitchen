"""Opik (self-hosted or Cloud): `opik.configure(...)` once at build time (factory), one
`OpikTracer` per run with the thread id so the Threads view groups the conversation."""

from typing import Any

from .models import RunInfo
from .tracer import Tracer


class OpikTracer(Tracer):
    def __init__(self, *, project_name: str, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.project_name = project_name

    def _callbacks(self, run: RunInfo) -> list[Any]:
        from opik.integrations.langchain import OpikTracer as OpikCallback  # lazy

        return [
            OpikCallback(
                project_name=self.project_name,
                thread_id=run.thread_id,
                tags=list(run.tags) or None,
                metadata={"tenant_id": run.tenant_id, "user_id": run.user_id, "request_id": run.request_id},
            )
        ]

    def _flush(self) -> None:
        import opik

        opik.flush_tracker()
