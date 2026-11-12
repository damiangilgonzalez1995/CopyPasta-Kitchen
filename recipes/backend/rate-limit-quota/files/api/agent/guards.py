"""Checks that run BEFORE a turn starts, in this order:

    1. endpoint enabled      (404: off means "there is nothing here")
    2. authenticated         (401, `get_current_user`)
    3. turn allowed          (429 quota exhausted or rate limited; add your 403 role checks here)

All of them before the stream opens: once the first SSE byte is out, the HTTP status is gone.

This file REPLACES `api/agent/guards.py` from `agent-chat-api`: step 3 asks the `TurnLimits`
stored in `app.state.turn_limits` (recipe `rate-limit-quota`). Without it, every turn is allowed.
"""

from fastapi import Depends, HTTPException, Request, status

from limits import QuotaExhausted, RateLimited, TurnLimits

from ..auth import CurrentUser, get_current_user
from .settings import AgentApiSettings


def get_agent_api_settings(request: Request) -> AgentApiSettings:
    settings: AgentApiSettings | None = getattr(request.app.state, "agent_api_settings", None)
    if settings is None:
        raise RuntimeError("app.state.agent_api_settings is not set: build the app with AgentApiSettings")
    return settings


def get_turn_limits(request: Request) -> TurnLimits | None:
    """`None` = no limits configured (tests, or a deployment that does not want them)."""
    return getattr(request.app.state, "turn_limits", None)


async def require_agent_enabled(settings: AgentApiSettings = Depends(get_agent_api_settings)) -> None:
    if not settings.agent_endpoint_enabled:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not Found")


async def ensure_turn_allowed(
    user: CurrentUser = Depends(get_current_user), limits: TurnLimits | None = Depends(get_turn_limits)
) -> CurrentUser:
    """Quota (per tenant) then rate limit (per user). 429 with the contract the frontend reads:

        {"code": "ai_quota_daily_exhausted" | "ai_quota_monthly_exhausted" | "rate_limited",
         "resets_at": "<ISO 8601>"}            (+ `Retry-After` header when rate limited)

    Role checks (403) go before `limits.allow`: a user without access must not spend quota.
    """
    if limits is None:
        return user
    try:
        await limits.allow(user.tenant_id, user.id)
    except QuotaExhausted as exc:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS, {"code": exc.code, "resets_at": exc.resets_at.isoformat()}
        ) from None
    except RateLimited as exc:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            {"code": exc.code, "resets_at": exc.resets_at.isoformat(), "retry_after": exc.retry_after},
            headers={"Retry-After": str(exc.retry_after)},
        ) from None
    return user
