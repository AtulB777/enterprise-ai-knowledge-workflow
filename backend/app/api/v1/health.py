"""Health check endpoint.

Deliberately minimal in Phase 2 — reports process liveness and configured
environment. Phase 3+ extends this to report real dependency health (DB, Redis,
LLM provider reachability) once those dependencies exist; until then it must not
falsely claim to have checked something it hasn't.
"""

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.core.config import Settings, get_settings

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: str
    app_name: str
    environment: str


@router.get("/health", response_model=HealthResponse)
async def health_check(
    settings: Annotated[Settings, Depends(get_settings)],
) -> HealthResponse:
    return HealthResponse(
        status="ok",
        app_name=settings.app_name,
        environment=settings.environment,
    )
