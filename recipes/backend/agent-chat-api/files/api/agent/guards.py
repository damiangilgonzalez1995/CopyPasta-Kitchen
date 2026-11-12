"""Checks that run BEFORE a turn starts, in this order:

    1. endpoint enabled      (404: off means "there is nothing here")
    2. authenticated         (401, `get_current_user`)
    3. turn allowed          (403 role without access, 429 quota or rate limit)

All of them before the stream opens: once the first SSE byte is out, the HTTP status is gone.
Step 3 is the extension point: the `rate-limit-quota` recipe (or your own rules) plugs in here.
"""

from fastapi import Depends, HTTPException, Request, status

from ..auth import CurrentUser, get_current_user
from .settings import AgentApiSettings


def get_agent_api_settings(request: Request) -> AgentApiSettings:
    settings: AgentApiSettings | None = getattr(request.app.state, "agent_api_settings", None)
    if settings is None:
        raise RuntimeError("app.state.agent_api_settings is not set: build the app with AgentApiSettings")
    return settings


async def require_agent_enabled(settings: AgentApiSettings = Depends(get_agent_api_settings)) -> None:
    if not settings.agent_endpoint_enabled:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not Found")


async def ensure_turn_allowed(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    """Role, quota and rate limit. Raise HTTPException(403/429) to refuse; return the user to allow.

    Replace it (or `app.dependency_overrides[ensure_turn_allowed] = ...`) with your rules. Anything that
    blocks (Redis, DB) goes through `run_in_threadpool` or an async client: never block the event loop.
    """
    return user
