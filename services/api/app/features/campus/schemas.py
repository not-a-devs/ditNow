"""Pydantic request/response DTOs. Envelopes use ``app.schemas.common``."""

from datetime import date
from typing import Self
from uuid import UUID

from pydantic import AwareDatetime, Field, model_validator

from app.features.campus.domain import (
    MAX_GRADE,
    MIN_GRADE,
    AcademicEvent,
    AcademicTerm,
    Audience,
    AudienceType,
    Channel,
    ChannelKind,
    DeliveryResult,
    MessageKind,
    Notice,
    NoticeStatus,
    SourceKind,
)
from app.features.campus.services import (
    MESSAGE_MAX_LENGTH,
    NOTICE_BODY_MAX_LENGTH,
    NOTICE_TITLE_MAX_LENGTH,
    MessageView,
)
from app.schemas.common import ApiModel


class AudienceModel(ApiModel):
    type: AudienceType
    department_id: UUID | None = None
    grade: int | None = Field(default=None, ge=MIN_GRADE, le=MAX_GRADE)

    @model_validator(mode="after")
    def check_shape(self) -> Self:
        self.to_domain()
        return self

    def to_domain(self) -> Audience:
        return Audience(self.type, self.department_id, self.grade)

    @classmethod
    def of(cls, audience: Audience) -> Self:
        return cls(type=audience.type, department_id=audience.department_id, grade=audience.grade)


class ChannelOut(ApiModel):
    id: UUID
    department_id: UUID
    kind: ChannelKind
    name: str
    grade: int | None

    @classmethod
    def of(cls, channel: Channel) -> Self:
        return cls(
            id=channel.id,
            department_id=channel.department_id,
            kind=channel.kind,
            name=channel.name,
            grade=channel.grade,
        )


class ChannelListData(ApiModel):
    items: list[ChannelOut]


class MessageCreate(ApiModel):
    body: str = Field(min_length=1, max_length=MESSAGE_MAX_LENGTH)
    client_nonce: str = Field(pattern=r"^[A-Za-z0-9_-]{8,64}$")


class NoticeCardOut(ApiModel):
    notice_id: UUID
    title: str
    status: NoticeStatus
    revision: int


class MessageOut(ApiModel):
    id: UUID
    channel_id: UUID
    seq: int
    kind: MessageKind
    body: str | None
    author_id: UUID | None
    is_mine: bool
    notice: NoticeCardOut | None
    created_at: AwareDatetime

    @classmethod
    def of(cls, view: MessageView) -> Self:
        message = view.message
        card = None
        if view.notice is not None:
            card = NoticeCardOut(
                notice_id=view.notice.id,
                title=view.notice.title,
                status=view.notice.status,
                revision=view.notice.revision,
            )
        return cls(
            id=message.id,
            channel_id=message.channel_id,
            seq=message.seq,
            kind=message.kind,
            body=message.body if message.kind is MessageKind.TEXT else None,
            author_id=message.author_id,
            is_mine=view.is_mine,
            notice=card,
            created_at=message.created_at,
        )


class MessageListData(ApiModel):
    items: list[MessageOut]
    next_before: int | None


class MessageSendData(ApiModel):
    message: MessageOut
    replayed: bool


class NoticeCreate(ApiModel):
    audience: AudienceModel
    title: str = Field(min_length=1, max_length=NOTICE_TITLE_MAX_LENGTH)
    body: str = Field(min_length=1, max_length=NOTICE_BODY_MAX_LENGTH)


class NoticeRevise(ApiModel):
    title: str = Field(min_length=1, max_length=NOTICE_TITLE_MAX_LENGTH)
    body: str = Field(min_length=1, max_length=NOTICE_BODY_MAX_LENGTH)
    expected_revision: int = Field(ge=1)


class NoticeTransition(ApiModel):
    """Publish/archive apply only to the revision the author last saw (409 otherwise)."""

    expected_revision: int = Field(ge=1)


class NoticeOut(ApiModel):
    id: UUID
    audience: AudienceModel
    title: str
    body: str
    status: NoticeStatus
    revision: int
    can_manage: bool
    created_at: AwareDatetime
    updated_at: AwareDatetime
    published_at: AwareDatetime | None

    @classmethod
    def of(cls, notice: Notice, *, can_manage: bool) -> Self:
        return cls(
            id=notice.id,
            audience=AudienceModel.of(notice.audience),
            title=notice.title,
            body=notice.body,
            status=notice.status,
            revision=notice.revision,
            can_manage=can_manage,
            created_at=notice.created_at,
            updated_at=notice.updated_at,
            published_at=notice.published_at,
        )


class NoticeListData(ApiModel):
    items: list[NoticeOut]


class DeliveryOut(ApiModel):
    channel_ids: list[UUID]
    created_count: int
    pending_target_count: int

    @classmethod
    def of(cls, result: DeliveryResult) -> Self:
        return cls(
            channel_ids=list(result.channel_ids),
            created_count=result.created_count,
            pending_target_count=len(result.missing_targets),
        )


class NoticePublishData(ApiModel):
    notice: NoticeOut
    delivery: DeliveryOut


class AcademicTermOut(ApiModel):
    id: UUID
    name: str
    starts_on: date
    ends_on: date
    source_kind: SourceKind
    source_url: str | None
    checked_at: AwareDatetime | None

    @classmethod
    def of(cls, term: AcademicTerm) -> Self:
        """Callers pass records already normalized by ``services.cited``."""
        return cls(
            id=term.id,
            name=term.name,
            starts_on=term.starts_on,
            ends_on=term.ends_on,
            source_kind=term.source_kind,
            source_url=term.source_url,
            checked_at=term.checked_at,
        )


class AcademicTermListData(ApiModel):
    items: list[AcademicTermOut]


class AcademicEventOut(ApiModel):
    id: UUID
    title: str
    starts_on: date
    ends_on: date
    source_kind: SourceKind
    source_url: str | None
    checked_at: AwareDatetime | None

    @classmethod
    def of(cls, event: AcademicEvent) -> Self:
        """Callers pass records already normalized by ``services.cited``."""
        return cls(
            id=event.id,
            title=event.title,
            starts_on=event.starts_on,
            ends_on=event.ends_on,
            source_kind=event.source_kind,
            source_url=event.source_url,
            checked_at=event.checked_at,
        )


class AcademicEventListData(ApiModel):
    term: AcademicTermOut
    items: list[AcademicEventOut]
