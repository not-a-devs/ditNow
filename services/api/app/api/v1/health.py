from fastapi import APIRouter

from app.schemas.common import SuccessResponse
from app.schemas.health import HealthData
from app.services.health import get_health

router = APIRouter()


@router.get("/health", response_model=SuccessResponse[HealthData], tags=["health"])
def health() -> SuccessResponse[HealthData]:
    """Process liveness only. Does not assert database/authentication readiness."""
    return SuccessResponse(data=get_health())
