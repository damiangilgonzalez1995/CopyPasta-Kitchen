"""`create_app(...)`: the FastAPI app with everything it needs injected.

Nothing is read from the environment here: the caller (your `main.py`, or a test) builds the
pieces from the project settings and passes them in. That is the test seam.

    # main.py
    settings = get_settings()                                   # project-settings
    app = create_app(
        settings=settings,                                      # inherits AgentApiSettings
        token_verifier=AuthFactory.create(settings),            # auth-verifier (or your subclass)
        memory=MemoryFactory.create(settings, session_factory=SessionLocal),
        document_search=my_search_service,
    )
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI

from agentic.graph import compile_graph
from agentic.llm import LLMSettings
from agentic.memory import Memory
from agentic.registry import registry

from .agent.router import router as agent_router
from .agent.settings import AgentApiSettings
from .auth import TokenVerifier


def create_app(
    *,
    settings: AgentApiSettings,
    token_verifier: TokenVerifier,
    memory: Memory,
    document_search: Any,
    llm_settings: LLMSettings | None = None,
    docs: bool = False,
) -> FastAPI:
    """`llm_settings=None` -> the project settings (`get_llm_settings()`); pass one only in tests.
    `docs=False` hides /docs and /openapi.json: enable it in development only."""

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        registry.configure(document_search=document_search, settings=llm_settings)
        compile_graph()
        yield

    app = FastAPI(
        title="{{app_name}}",
        lifespan=lifespan,
        docs_url="/docs" if docs else None,
        redoc_url=None,
        openapi_url="/openapi.json" if docs else None,
    )
    app.state.agent_api_settings = settings
    app.state.token_verifier = token_verifier
    app.state.memory = memory
    app.include_router(agent_router)
    return app
