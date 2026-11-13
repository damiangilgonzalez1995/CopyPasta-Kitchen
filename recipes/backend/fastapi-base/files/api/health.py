"""GET /health: liveness, no auth, no dependencies. Readiness checks (DB, LLM provider) are a
different route with their own timeouts; a liveness probe that touches the DB takes the API
down with the DB."""

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    status: str = "ok"


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse()
