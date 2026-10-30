"""FR-CAMP-002 manual travel calculator routes (mounted by the root owner under ``/api/v1``).

Fails closed with 503 ``UNAVAILABLE`` unless ``enabled=True``. When the root injects the
current common ``actor`` provider, an unauthenticated caller gets 401 before any calculation.
The calculation itself is stateless: no persistence, map distance or academic data.
"""

from collections.abc import Callable
from typing import Annotated, Any

from fastapi import APIRouter, Depends

from app.core.errors import ApiError
from app.features.campus_travel.models import TravelInput, TravelResult
from app.features.campus_travel.service import calculate_travel
from app.features.collaboration.router import PrivateNoStoreRoute
from app.schemas.common import ErrorCode, ErrorResponse, SuccessResponse

CALCULATE_PATH = "/campus-travel/calculate"


def no_actor_required() -> None:
    return None


def build_travel_router(
    *, enabled: bool = False, actor: Callable[..., Any] | None = None
) -> APIRouter:
    """``actor`` is the server-side current-identity dependency; it is never read from the body."""
    router = APIRouter(
        tags=["campus-travel-manual"],
        route_class=PrivateNoStoreRoute,
        responses={s: {"model": ErrorResponse} for s in (400, 401, 500, 503)},
    )

    def current_actor(
        value: Annotated[Any, Depends(actor or no_actor_required)],
    ) -> None:
        if actor is not None and (value is None or not getattr(value, "user_id", None)):
            raise ApiError(ErrorCode.UNAUTHORIZED)

    def available() -> None:
        if not enabled:
            raise ApiError(ErrorCode.UNAVAILABLE)

    # Availability is decided before identity so a disabled router never touches auth.
    @router.post(
        CALCULATE_PATH,
        response_model=SuccessResponse[TravelResult],
        dependencies=[Depends(available), Depends(current_actor)],
    )
    def calculate(value: TravelInput):
        return SuccessResponse(data=calculate_travel(value))

    return router


router = build_travel_router()

__all__ = ["CALCULATE_PATH", "build_travel_router", "router"]
