from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query

from app.core.errors import ApiError
from app.features.classrooms.models import ClassroomActor
from app.features.classrooms.router import PrivateClassroomRoute, get_classroom_actor
from app.features.screen_sharing.models import (
    ContextView,
    ReconnectInput,
    RevisionInput,
    SessionView,
    SignalInput,
    SignalPage,
)
from app.features.screen_sharing.service import KEY_PATTERN, ScreenSharingService
from app.schemas.common import ErrorCode, SuccessResponse


def get_screen_sharing_service() -> ScreenSharingService:
    """Requires approved transactional common enrollment store and signaling transport."""
    raise ApiError(ErrorCode.UNAVAILABLE)


Actor = Annotated[ClassroomActor, Depends(get_classroom_actor)]
Service = Annotated[ScreenSharingService, Depends(get_screen_sharing_service)]
Key = Annotated[str, Header(alias="Idempotency-Key", pattern=KEY_PATTERN)]
router = APIRouter(
    prefix="/screen-sharing", tags=["screen-sharing-first-pass"], route_class=PrivateClassroomRoute
)


@router.get("/{offering_id}", response_model=SuccessResponse[ContextView])
def context(offering_id: UUID, actor: Actor, service: Service):
    return SuccessResponse(data=service.context(actor, offering_id))


@router.post("/{offering_id}/sessions", response_model=SuccessResponse[SessionView])
def start(offering_id: UUID, actor: Actor, service: Service, key: Key):
    return SuccessResponse(data=service.start(actor, offering_id, key))


@router.post(
    "/{offering_id}/sessions/{session_id}/activate", response_model=SuccessResponse[SessionView]
)
def activate(
    offering_id: UUID, session_id: UUID, body: RevisionInput, actor: Actor, service: Service
):
    return SuccessResponse(
        data=service.state(actor, offering_id, session_id, body.expected_revision)
    )


@router.post(
    "/{offering_id}/sessions/{session_id}/end", response_model=SuccessResponse[SessionView]
)
def end(offering_id: UUID, session_id: UUID, body: RevisionInput, actor: Actor, service: Service):
    return SuccessResponse(
        data=service.state(actor, offering_id, session_id, body.expected_revision, True)
    )


@router.post(
    "/{offering_id}/sessions/{session_id}/join", response_model=SuccessResponse[SessionView]
)
def join(offering_id: UUID, session_id: UUID, actor: Actor, service: Service, key: Key):
    return SuccessResponse(data=service.join(actor, offering_id, session_id, key))


@router.post(
    "/{offering_id}/sessions/{session_id}/reconnect", response_model=SuccessResponse[SessionView]
)
def reconnect(
    offering_id: UUID,
    session_id: UUID,
    body: ReconnectInput,
    actor: Actor,
    service: Service,
    key: Key,
):
    return SuccessResponse(
        data=service.join(actor, offering_id, session_id, key, body.expected_generation)
    )


@router.post("/{offering_id}/sessions/{session_id}/leave", response_model=SuccessResponse[None])
def leave(
    offering_id: UUID, session_id: UUID, body: ReconnectInput, actor: Actor, service: Service
):
    service.leave(actor, offering_id, session_id, body.expected_generation)
    return SuccessResponse[None](data=None)


@router.post(
    "/{offering_id}/sessions/{session_id}/revoke/{peer_id}", response_model=SuccessResponse[None]
)
def revoke(
    offering_id: UUID,
    session_id: UUID,
    peer_id: UUID,
    body: ReconnectInput,
    actor: Actor,
    service: Service,
):
    service.leave(actor, offering_id, session_id, body.expected_generation, peer_id)
    return SuccessResponse[None](data=None)


@router.post("/{offering_id}/sessions/{session_id}/signals", response_model=SuccessResponse[int])
def send_signal(
    offering_id: UUID, session_id: UUID, body: SignalInput, actor: Actor, service: Service, key: Key
):
    return SuccessResponse(data=service.signal(actor, offering_id, session_id, body, key))


@router.get(
    "/{offering_id}/sessions/{session_id}/signals", response_model=SuccessResponse[SignalPage]
)
def poll_signals(
    offering_id: UUID,
    session_id: UUID,
    actor: Actor,
    service: Service,
    generation: Annotated[int, Query(ge=1)],
    after: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=50)] = 25,
):
    return SuccessResponse(
        data=service.signals(actor, offering_id, session_id, generation, after, limit)
    )
