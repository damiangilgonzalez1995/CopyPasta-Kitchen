"""`create_app(...)`: the project's app. Everything it needs is injected; nothing reads the environment.

    # main.py
    settings = get_settings()                      # project-settings, with ApiSettings mixed in
    configure_logging(settings.log_level)
    app = create_app(settings=settings)

Other recipes replace this file with a `create_app` that takes their services (`agent-chat-api`
takes the token verifier and the memory) and still starts from `build_app`.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from .base import build_app
from .settings import ApiSettings


def create_app(*, settings: ApiSettings, docs: bool | None = None) -> FastAPI:
    """`docs=None` -> `settings.docs_enabled`."""

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        # Open what the app needs (DB engine, HTTP clients) and put it in app.state; close it after yield.
        yield

    app = build_app(
        title="{{app_name}}",
        lifespan=lifespan,
        docs=settings.docs_enabled if docs is None else docs,
        cors_origins=settings.cors_origins,
    )
    app.state.api_settings = settings
    # app.include_router(my_router)
    return app
