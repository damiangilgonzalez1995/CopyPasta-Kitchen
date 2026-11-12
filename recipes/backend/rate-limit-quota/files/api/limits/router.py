"""GET /agent/quota: can this tenant ask right now, and if not, until when.

The chat UI calls it on load (and after a 429) to lock the composer until `resets_at`.
Same guards as the chat routes (404 when the agent is off, 401 without token). Mount it next to
the chat router: `app.include_router(quota_router)` after `create_app(...)`.
"""

from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict

from limits import QuotaPeriod, TurnLimits

from ..agent.guards import get_turn_limits, require_agent_enabled
from ..auth import CurrentUser, get_current_user

router = APIRouter(prefix="/agent", tags=["agent"], dependencies=[Depends(require_agent_enabled)])


class QuotaResponse(BaseModel):
    """`exhausted` is the period that blocks (`daily` | `monthly`); `resets_at` only when blocked."""

    model_config = ConfigDict(frozen=True)

    available: bool
    exhausted: QuotaPeriod | None = None
    resets_at: datetime | None = None


@router.get("/quota", response_model=QuotaResponse)
async def quota(
    user: CurrentUser = Depends(get_current_user), limits: TurnLimits | None = Depends(get_turn_limits)
) -> QuotaResponse:
    if limits is None:
        return QuotaResponse(available=True)
    status = await limits.status(user.tenant_id)
    return QuotaResponse(available=status.available, exhausted=status.exhausted, resets_at=status.resets_at)
