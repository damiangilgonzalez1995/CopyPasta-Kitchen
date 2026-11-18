"""Langfuse (SDK v3+): one `Langfuse` client per process, one `CallbackHandler` per run.
Session = thread_id, user = user_id, both through the metadata keys the handler understands."""

from typing import Any

from .models import RunInfo
from .tracer import Tracer


class LangfuseTracer(Tracer):
    def __init__(self, client: Any, *, public_key: str, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._client = client
        self._public_key = public_key

    def _callbacks(self, run: RunInfo) -> list[Any]:
        from langfuse.langchain import CallbackHandler  # lazy: install `langfuse` only if you use it

        return [CallbackHandler(public_key=self._public_key)]

    def _metadata(self, run: RunInfo) -> dict[str, Any]:
        return {
            "langfuse_session_id": run.thread_id,
            "langfuse_user_id": run.user_id,
            "langfuse_tags": list(run.tags),
        }

    def _flush(self) -> None:
        self._client.flush()
