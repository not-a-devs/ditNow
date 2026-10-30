"""Demo activity-preference routes (not mounted; the root owner includes this under ``/api/v1``).

Both dependencies fail closed with 503 ``UNAVAILABLE``. The root owner overrides ``get_actor``
with the current common actor's UUID and sets ``app.state.demo_profile = DemoProfileStore()``.
The owner is always that injected UUID; no actor, department or role is read from the request.
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request

from app.core.errors import ApiError
from app.features.collaboration.router import PrivateNoStoreRoute
from app.features.demo_profile.schemas import DemoProfilePreferences, DemoProfileUpdate
from app.features.demo_profile.store import DemoProfileStore
from app.schemas.common import ErrorCode, ErrorResponse, SuccessResponse

PATH = "/me/demo-profile"


def get_actor() -> UUID | None:
    raise ApiError(ErrorCode.UNAVAILABLE)


def current_owner(actor: Annotated[UUID | None, Depends(get_actor)]) -> UUID:
    if not isinstance(actor, UUID):
        raise ApiError(ErrorCode.UNAUTHORIZED)
    return actor


Owner = Annotated[UUID, Depends(current_owner)]


def get_store(_: Owner, request: Request) -> DemoProfileStore:
    # Authentication is decided before the store is ever resolved.
    store = getattr(request.app.state, "demo_profile", None)
    if not isinstance(store, DemoProfileStore):
        raise ApiError(ErrorCode.UNAVAILABLE)
    return store


Store = Annotated[DemoProfileStore, Depends(get_store)]

router = APIRouter(
    tags=["demo-profile"],
    route_class=PrivateNoStoreRoute,
    responses={code: {"model": ErrorResponse} for code in (400, 401, 409, 500, 503)},
)


@router.get(PATH, response_model=SuccessResponse[DemoProfilePreferences])
def read_demo_profile(owner: Owner, store: Store):
    preferences = store.get(owner)
    return SuccessResponse(data=preferences, resource_version=preferences.revision)


@router.patch(PATH, response_model=SuccessResponse[DemoProfilePreferences])
def update_demo_profile(owner: Owner, store: Store, payload: DemoProfileUpdate):
    preferences = store.update(owner, payload)
    return SuccessResponse(data=preferences, resource_version=preferences.revision)
