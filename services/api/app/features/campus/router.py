"""Campus HTTP routes. Mounting under ``/api/v1`` is owned by the root integrator.

``router`` (no runtime) fails closed with 503 for every route. A real runtime must be injected
through ``build_campus_router`` once shared auth and DB adapters exist.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response, status

from app.core.errors import ApiError
from app.features.campus import policy
from app.features.campus.domain import CampusActor
from app.features.campus.repositories import (
    AcademicCalendarRepository,
    ActorResolver,
    ChannelRepository,
    MessageRepository,
    NoticeRepository,
)
from app.features.campus.schemas import (
    AcademicEventListData,
    AcademicEventOut,
    AcademicTermListData,
    AcademicTermOut,
    ChannelListData,
    ChannelOut,
    DeliveryOut,
    MessageCreate,
    MessageListData,
    MessageOut,
    MessageSendData,
    NoticeCreate,
    NoticeListData,
    NoticeOut,
    NoticePublishData,
    NoticeRevise,
)
from app.features.campus.services import (
    AcademicService,
    ChatService,
    Clock,
    NoticeService,
    system_clock,
)
from app.schemas.common import ErrorCode, ErrorResponse, SuccessResponse


@dataclass(frozen=True, slots=True)
class CampusRuntime:
    actor_resolver: ActorResolver
    channels: ChannelRepository
    messages: MessageRepository
    notices: NoticeRepository
    calendar: AcademicCalendarRepository
    clock: Clock = system_clock


type RuntimeProvider = Callable[[], CampusRuntime]

ERROR_RESPONSES: dict[int | str, dict[str, object]] = {
    code: {"model": ErrorResponse} for code in (401, 403, 404, 409, 503)
}


def build_campus_router(provider: RuntimeProvider | None = None) -> APIRouter:
    router = APIRouter(tags=["campus"], responses=ERROR_RESPONSES)

    def runtime() -> CampusRuntime:
        if provider is None:
            # Shared auth/DB not connected: refuse instead of serving unauthenticated data.
            raise ApiError(ErrorCode.UNAVAILABLE)
        return provider()

    def actor(request: Request, rt: Annotated[CampusRuntime, Depends(runtime)]) -> CampusActor:
        resolved = rt.actor_resolver.resolve(request)
        if resolved is None:
            raise ApiError(ErrorCode.UNAUTHORIZED)
        return resolved

    Runtime = Annotated[CampusRuntime, Depends(runtime)]
    Actor = Annotated[CampusActor, Depends(actor)]

    def chat(rt: CampusRuntime) -> ChatService:
        return ChatService(rt.channels, rt.messages, rt.notices, rt.clock)

    def notices(rt: CampusRuntime) -> NoticeService:
        return NoticeService(rt.notices, rt.channels, rt.messages, rt.clock)

    @router.get(
        "/departments/{department_id}/channels",
        response_model=SuccessResponse[ChannelListData],
    )
    def list_channels(
        department_id: UUID, me: Actor, rt: Runtime
    ) -> SuccessResponse[ChannelListData]:
        items = chat(rt).list_department_channels(me, department_id)
        return SuccessResponse(data=ChannelListData(items=[ChannelOut.of(c) for c in items]))

    @router.get("/channels/{channel_id}/messages", response_model=SuccessResponse[MessageListData])
    def list_messages(
        channel_id: UUID,
        me: Actor,
        rt: Runtime,
        before: Annotated[int | None, Query(ge=1)] = None,
        limit: Annotated[int, Query(ge=1, le=100)] = 50,
    ) -> SuccessResponse[MessageListData]:
        page = chat(rt).list_messages(me, channel_id, before, limit)
        return SuccessResponse(
            data=MessageListData(
                items=[MessageOut.of(item) for item in page.items], next_before=page.next_before
            )
        )

    @router.post(
        "/channels/{channel_id}/messages",
        response_model=SuccessResponse[MessageSendData],
        status_code=status.HTTP_201_CREATED,
    )
    def send_message(
        channel_id: UUID, payload: MessageCreate, me: Actor, rt: Runtime, response: Response
    ) -> SuccessResponse[MessageSendData]:
        view, created = chat(rt).send_message(me, channel_id, payload.body, payload.client_nonce)
        if not created:
            response.status_code = status.HTTP_200_OK
        return SuccessResponse(
            data=MessageSendData(message=MessageOut.of(view), replayed=not created)
        )

    @router.get("/notices", response_model=SuccessResponse[NoticeListData])
    def list_notices(
        me: Actor, rt: Runtime, limit: Annotated[int, Query(ge=1, le=50)] = 20
    ) -> SuccessResponse[NoticeListData]:
        items = notices(rt).list_for(me, limit)
        return SuccessResponse(
            data=NoticeListData(
                items=[NoticeOut.of(n, can_manage=policy.can_author(me, n.audience)) for n in items]
            )
        )

    @router.post(
        "/notices",
        response_model=SuccessResponse[NoticeOut],
        status_code=status.HTTP_201_CREATED,
    )
    def create_notice(payload: NoticeCreate, me: Actor, rt: Runtime) -> SuccessResponse[NoticeOut]:
        notice = notices(rt).create_draft(
            me, payload.audience.to_domain(), payload.title, payload.body
        )
        return SuccessResponse(
            data=NoticeOut.of(notice, can_manage=True), resource_version=notice.revision
        )

    @router.get("/notices/{notice_id}", response_model=SuccessResponse[NoticeOut])
    def get_notice(notice_id: UUID, me: Actor, rt: Runtime) -> SuccessResponse[NoticeOut]:
        notice = notices(rt).get(me, notice_id)
        return SuccessResponse(
            data=NoticeOut.of(notice, can_manage=policy.can_author(me, notice.audience)),
            resource_version=notice.revision,
        )

    @router.patch("/notices/{notice_id}", response_model=SuccessResponse[NoticeOut])
    def revise_notice(
        notice_id: UUID, payload: NoticeRevise, me: Actor, rt: Runtime
    ) -> SuccessResponse[NoticeOut]:
        notice = notices(rt).revise(
            me, notice_id, payload.title, payload.body, payload.expected_revision
        )
        return SuccessResponse(
            data=NoticeOut.of(notice, can_manage=True), resource_version=notice.revision
        )

    @router.post("/notices/{notice_id}/publish", response_model=SuccessResponse[NoticePublishData])
    def publish_notice(
        notice_id: UUID, me: Actor, rt: Runtime
    ) -> SuccessResponse[NoticePublishData]:
        notice, delivery = notices(rt).publish(me, notice_id)
        return SuccessResponse(
            data=NoticePublishData(
                notice=NoticeOut.of(notice, can_manage=True), delivery=DeliveryOut.of(delivery)
            ),
            resource_version=notice.revision,
        )

    @router.post("/notices/{notice_id}/archive", response_model=SuccessResponse[NoticeOut])
    def archive_notice(notice_id: UUID, me: Actor, rt: Runtime) -> SuccessResponse[NoticeOut]:
        notice = notices(rt).archive(me, notice_id)
        return SuccessResponse(
            data=NoticeOut.of(notice, can_manage=True), resource_version=notice.revision
        )

    @router.get("/academic/terms", response_model=SuccessResponse[AcademicTermListData])
    def list_terms(me: Actor, rt: Runtime) -> SuccessResponse[AcademicTermListData]:
        terms = AcademicService(rt.calendar).list_terms(me)
        return SuccessResponse(
            data=AcademicTermListData(items=[AcademicTermOut.of(t) for t in terms])
        )

    @router.get(
        "/academic/terms/{term_id}/events",
        response_model=SuccessResponse[AcademicEventListData],
    )
    def list_events(
        term_id: UUID,
        me: Actor,
        rt: Runtime,
        from_date: Annotated[date | None, Query(alias="from")] = None,
        to_date: Annotated[date | None, Query(alias="to")] = None,
    ) -> SuccessResponse[AcademicEventListData]:
        term, events = AcademicService(rt.calendar).list_events(me, term_id, from_date, to_date)
        return SuccessResponse(
            data=AcademicEventListData(
                term=AcademicTermOut.of(term), items=[AcademicEventOut.of(e) for e in events]
            )
        )

    return router


router = build_campus_router()
