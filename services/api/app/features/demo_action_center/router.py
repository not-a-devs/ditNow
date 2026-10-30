"""DEMO action-center routes (not mounted; the root includes this under ``/api/v1``).

Defaults fail closed with 503: the root overrides ``get_actor`` with the common current actor
and installs ``DemoActionCenterStore`` on ``app.state.demo_action_center``. No header, query or
body field can choose the actor, department or role.
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request

from app.core.errors import ApiError
from app.features.collaboration.router import PrivateNoStoreRoute
from app.features.demo_action_center.models import DemoReadInput, DemoReadResult, DemoSummary
from app.features.demo_action_center.store import DemoActionCenterStore
from app.schemas.common import ErrorCode, ErrorResponse, SuccessResponse


def get_actor() -> UUID:
    """Only the approved common identity bridge can supply this."""
    raise ApiError(ErrorCode.UNAVAILABLE)


def get_store(request: Request) -> DemoActionCenterStore:
    store = getattr(request.app.state, "demo_action_center", None)
    if not isinstance(store, DemoActionCenterStore):
        raise ApiError(ErrorCode.UNAVAILABLE)
    return store


def current_actor(actor: Annotated[UUID | None, Depends(get_actor)]) -> UUID:
    if not isinstance(actor, UUID):
        raise ApiError(ErrorCode.UNAUTHORIZED)
    return actor


def demo_store(
    _: Annotated[UUID, Depends(current_actor)],  # identity is decided before the store
    store: Annotated[DemoActionCenterStore, Depends(get_store)],
) -> DemoActionCenterStore:
    return store


Actor = Annotated[UUID, Depends(current_actor)]
Store = Annotated[DemoActionCenterStore, Depends(demo_store)]

router = APIRouter(
    prefix="/me/demo-action-center",
    tags=["demo-action-center"],
    route_class=PrivateNoStoreRoute,
    responses={code: {"model": ErrorResponse} for code in (400, 401, 404, 409, 500, 503)},
)


@router.get("/summary", response_model=SuccessResponse[DemoSummary])
def summary(actor: Actor, store: Store):
    return SuccessResponse(data=store.summary(actor))


@router.post(
    "/notifications/{notification_id}/read", response_model=SuccessResponse[DemoReadResult]
)
def read(notification_id: UUID, body: DemoReadInput, actor: Actor, store: Store):
    result = store.mark_read(actor, notification_id, body.revision)
    return SuccessResponse(data=result, resource_version=result.notification.revision)
