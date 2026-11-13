"""`build_app(...)`: a FastAPI app with the plumbing every backend here has, and nothing else.

    request id on every request, response and log line   (request_id.py)
    unexpected failures as 500 without internals           (request_id.py)
    CORS only when origins are configured
    GET /health
    /docs and /openapi.json only when asked for

Your `create_app` (see `app.py`) calls it, then puts services in `app.state` and includes routers.
Nothing is read from the environment here: the caller passes what it wants.
"""

from collections.abc import Callable, Sequence
from contextlib import AbstractAsyncContextManager
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .health import router as health_router
from .request_id import install_request_id

Lifespan = Callable[[FastAPI], AbstractAsyncContextManager[Any]]


def build_app(
    *,
    title: str,
    lifespan: Lifespan | None = None,
    docs: bool = False,
    cors_origins: Sequence[str] = (),
    version: str = "0.1.0",
) -> FastAPI:
    app = FastAPI(
        title=title,
        version=version,
        lifespan=lifespan,
        docs_url="/docs" if docs else None,
        redoc_url=None,
        openapi_url="/openapi.json" if docs else None,
    )
    if cors_origins:
        # Added first so it ends up outermost: the preflight OPTIONS is answered before anything else.
        app.add_middleware(
            CORSMiddleware,
            allow_origins=list(cors_origins),
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
            expose_headers=["X-Request-ID", "Retry-After"],
        )
    install_request_id(app)
    app.include_router(health_router)
    return app
