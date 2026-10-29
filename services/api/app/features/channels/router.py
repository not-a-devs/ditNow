"""Free channel routes (dormant). Mounting under ``/api/v1`` is owned by the root integrator.

Both dependencies fail closed with 503 until the shared auth bridge and an approved MariaDB
unit of work are wired. There is no approval, official-badge or staff-claim endpoint.
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Response, status

from app.core.errors import ApiError
from app.features.academics.idempotency import KEY_PATTERN
from app.features.channels.domain import PAGE_MAX, ChannelsActor
from app.features.channels.schemas import (
    ChannelArchive,
    ChannelCreate,
    ChannelPageOut,
    ChannelUpdate,
    CreatedChannelOut,
    CreatedRequestOut,
    FreeChannelOut,
    MembershipOut,
    OfficialRequestCreate,
    OfficialRequestOut,
    RequestPageOut,
)
from app.features.channels.service import ChannelPage, ChannelsService, MembershipResult

# Shared no-store wrapper (success and error responses) instead of another copy of it.
from app.features.collaboration.router import PrivateNoStoreRoute
from app.schemas.common import ErrorCode, ErrorResponse, SuccessResponse

router = APIRouter(
    tags=["channels-first-pass"],
    route_class=PrivateNoStoreRoute,
    responses={code: {"model": ErrorResponse} for code in (400, 401, 403, 404, 409, 500, 503)},
)


def get_channels_actor() -> ChannelsActor | None:
    """Approved common auth bridge required: verified session -> user ID. ``None`` -> 401.

    Never trust client-supplied user, department, grade or role headers.
    """
    raise ApiError(ErrorCode.UNAVAILABLE)


def get_channels_service() -> ChannelsService:
    """Approved transactional ChannelsStore (MariaDB) required; no runtime fake exists."""
    raise ApiError(ErrorCode.UNAVAILABLE)


def _service_first(service: Annotated[ChannelsService, Depends(get_channels_service)]):
    return service


def _actor(
    _: Annotated[ChannelsService, Depends(_service_first)],
    actor: Annotated[ChannelsActor | None, Depends(get_channels_actor)],
) -> ChannelsActor:
    # Service availability is checked before identity so an unwired module is always 503.
    if actor is None:
        raise ApiError(ErrorCode.UNAUTHORIZED)
    return actor


Actor = Annotated[ChannelsActor, Depends(_actor)]
Service = Annotated[ChannelsService, Depends(_service_first)]
IdempotencyKey = Annotated[str, Header(pattern=KEY_PATTERN)]
Limit = Annotated[int, Query(ge=1, le=PAGE_MAX)]
Before = Annotated[int | None, Query(ge=1)]


def _page(page: ChannelPage) -> SuccessResponse[ChannelPageOut]:
    return SuccessResponse(
        data=ChannelPageOut(
            items=[FreeChannelOut.of(v) for v in page.items], next_before=page.next_before
        )
    )


def _membership(result: MembershipResult) -> SuccessResponse[MembershipOut]:
    return SuccessResponse(
        data=MembershipOut(channel=FreeChannelOut.of(result.channel), changed=result.changed)
    )


@router.get(
    "/departments/{department_id}/free-channels", response_model=SuccessResponse[ChannelPageOut]
)
def list_department(
    department_id: UUID, actor: Actor, service: Service, before: Before = None, limit: Limit = 20
):
    return _page(service.list_department(actor, department_id, before, limit))


@router.get("/me/free-channels", response_model=SuccessResponse[ChannelPageOut])
def my_channels(actor: Actor, service: Service, before: Before = None, limit: Limit = 20):
    return _page(service.my_channels(actor, before, limit))


@router.post(
    "/free-channels",
    response_model=SuccessResponse[CreatedChannelOut],
    status_code=status.HTTP_201_CREATED,
)
def create_channel(
    body: ChannelCreate,
    actor: Actor,
    service: Service,
    idempotency_key: IdempotencyKey,
    response: Response,
):
    result = service.create(
        actor, body.department_id, body.grade, body.name, body.description, idempotency_key
    )
    if result.replayed:
        response.status_code = status.HTTP_200_OK
    out = FreeChannelOut.of(result.value)
    return SuccessResponse(
        data=CreatedChannelOut(channel=out, replayed=result.replayed), resource_version=out.revision
    )


@router.get("/free-channels/{channel_id}", response_model=SuccessResponse[FreeChannelOut])
def get_channel(channel_id: UUID, actor: Actor, service: Service):
    out = FreeChannelOut.of(service.get(actor, channel_id))
    return SuccessResponse(data=out, resource_version=out.revision)


@router.patch("/free-channels/{channel_id}", response_model=SuccessResponse[FreeChannelOut])
def update_channel(channel_id: UUID, body: ChannelUpdate, actor: Actor, service: Service):
    view = service.update(actor, channel_id, body.name, body.description, body.expected_revision)
    out = FreeChannelOut.of(view)
    return SuccessResponse(data=out, resource_version=out.revision)


@router.post("/free-channels/{channel_id}/archive", response_model=SuccessResponse[FreeChannelOut])
def archive_channel(channel_id: UUID, body: ChannelArchive, actor: Actor, service: Service):
    out = FreeChannelOut.of(service.archive(actor, channel_id, body.expected_revision))
    return SuccessResponse(data=out, resource_version=out.revision)


@router.post("/free-channels/{channel_id}/join", response_model=SuccessResponse[MembershipOut])
def join_channel(channel_id: UUID, actor: Actor, service: Service):
    return _membership(service.join(actor, channel_id))


@router.post("/free-channels/{channel_id}/leave", response_model=SuccessResponse[MembershipOut])
def leave_channel(channel_id: UUID, actor: Actor, service: Service):
    return _membership(service.leave(actor, channel_id))


@router.post(
    "/free-channels/{channel_id}/official-requests",
    response_model=SuccessResponse[CreatedRequestOut],
    status_code=status.HTTP_201_CREATED,
)
def request_official(
    channel_id: UUID,
    body: OfficialRequestCreate,
    actor: Actor,
    service: Service,
    idempotency_key: IdempotencyKey,
    response: Response,
):
    result = service.request_official(actor, channel_id, body.reason, idempotency_key)
    if result.replayed:
        response.status_code = status.HTTP_200_OK
    return SuccessResponse(
        data=CreatedRequestOut(
            request=OfficialRequestOut.of(result.value), replayed=result.replayed
        )
    )


@router.get("/me/official-channel-requests", response_model=SuccessResponse[RequestPageOut])
def my_requests(actor: Actor, service: Service, before: Before = None, limit: Limit = 20):
    page = service.my_requests(actor, before, limit)
    return SuccessResponse(
        data=RequestPageOut(
            items=[OfficialRequestOut.of(r) for r in page.items], next_before=page.next_before
        )
    )


@router.get(
    "/me/official-channel-requests/{request_id}",
    response_model=SuccessResponse[OfficialRequestOut],
)
def get_request(request_id: UUID, actor: Actor, service: Service):
    return SuccessResponse(data=OfficialRequestOut.of(service.get_request(actor, request_id)))
