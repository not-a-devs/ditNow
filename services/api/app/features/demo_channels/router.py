"""DEMO channel-request routes (not mounted; the root owner includes this under ``/api/v1``).

Defaults fail closed with 503: the root overrides ``get_actor`` with the current common actor's
UUID and sets ``app.state.demo_channels = DemoChannelsStore()``. No actor, department, or role
is ever read from the client. Every response carries ``Cache-Control: private, no-store``.
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, status

from app.core.errors import ApiError
from app.features.collaboration.router import PrivateNoStoreRoute
from app.schemas.common import ErrorCode, ErrorResponse, SuccessResponse

from .models import (
    DemoChannelRequestCancelled,
    DemoChannelRequestCreate,
    DemoChannelRequestList,
    DemoChannelRequestView,
)
from .store import DemoChannelsStore

router = APIRouter(
    prefix="/me/demo-channels",
    tags=["demo-channels"],
    route_class=PrivateNoStoreRoute,
    responses={code: {"model": ErrorResponse} for code in (400, 401, 404, 409, 500, 503)},
)


def get_actor() -> UUID | None:
    raise ApiError(ErrorCode.UNAVAILABLE)


def current_actor(actor: Annotated[UUID | None, Depends(get_actor)]) -> UUID:
    if not isinstance(actor, UUID):
        raise ApiError(ErrorCode.UNAUTHORIZED)
    return actor


def get_store(request: Request, _: Annotated[UUID, Depends(current_actor)]) -> DemoChannelsStore:
    store = getattr(request.app.state, "demo_channels", None)
    if not isinstance(store, DemoChannelsStore):
        raise ApiError(ErrorCode.UNAVAILABLE)
    return store


Actor = Annotated[UUID, Depends(current_actor)]
Store = Annotated[DemoChannelsStore, Depends(get_store)]


@router.get("", response_model=SuccessResponse[DemoChannelRequestList])
def list_my_demo_channel_requests(actor: Actor, store: Store):
    return SuccessResponse(data=DemoChannelRequestList(items=store.list_own(actor)))


@router.post(
    "",
    response_model=SuccessResponse[DemoChannelRequestView],
    status_code=status.HTTP_201_CREATED,
)
def create_demo_channel_request(actor: Actor, store: Store, body: DemoChannelRequestCreate):
    created = store.create(actor, body)
    return SuccessResponse(data=created, resource_version=created.revision)


@router.delete("/{request_id}", response_model=SuccessResponse[DemoChannelRequestCancelled])
def cancel_demo_channel_request(
    actor: Actor,
    store: Store,
    request_id: UUID,
    revision: Annotated[int, Query(ge=1, le=1_000_000)],
):
    return SuccessResponse(
        data=DemoChannelRequestCancelled(id=store.cancel(actor, request_id, revision))
    )
