"""Request/response DTOs. Owner/requester user IDs are never returned; only the caller's role."""

from typing import Literal, Self
from uuid import UUID

from pydantic import AwareDatetime, Field

from app.features.campus.domain import MAX_GRADE, MIN_GRADE
from app.features.channels.domain import (
    DESCRIPTION_MAX_LENGTH,
    NAME_MAX_LENGTH,
    REASON_MAX_LENGTH,
    REVIEW_BLOCKED,
    ChannelStatus,
    MemberRole,
    OfficialChannelRequest,
    RequestStatus,
)
from app.features.channels.service import ChannelView
from app.schemas.common import ApiModel

# Server-side lengths are counted after NFC normalization; these bounds only stop oversized
# payloads early (a few code points of slack for normalization that shortens text).
_SLACK = 16


class ChannelCreate(ApiModel):
    department_id: UUID
    grade: int | None = Field(default=None, ge=MIN_GRADE, le=MAX_GRADE)
    name: str = Field(min_length=1, max_length=NAME_MAX_LENGTH + _SLACK)
    description: str = Field(default="", max_length=DESCRIPTION_MAX_LENGTH + _SLACK)


class ChannelUpdate(ApiModel):
    name: str = Field(min_length=1, max_length=NAME_MAX_LENGTH + _SLACK)
    description: str = Field(default="", max_length=DESCRIPTION_MAX_LENGTH + _SLACK)
    expected_revision: int = Field(ge=1)


class ChannelArchive(ApiModel):
    expected_revision: int = Field(ge=1)


class OfficialRequestCreate(ApiModel):
    reason: str = Field(min_length=1, max_length=REASON_MAX_LENGTH + _SLACK)


class FreeChannelOut(ApiModel):
    id: UUID
    department_id: UUID
    grade: int | None
    kind: Literal["FREE"] = "FREE"
    # Official status/badges cannot be granted in this pass; the type itself forbids True.
    is_official: Literal[False] = False
    name: str
    description: str
    status: ChannelStatus
    revision: int
    member_count: int
    my_role: MemberRole | None
    created_at: AwareDatetime
    archived_at: AwareDatetime | None

    @classmethod
    def of(cls, view: ChannelView) -> Self:
        c = view.channel
        return cls(
            id=c.id,
            department_id=c.department_id,
            grade=c.grade,
            name=c.name,
            description=c.description,
            status=c.status,
            revision=c.revision,
            member_count=c.member_count,
            my_role=view.my_role,
            created_at=c.created_at,
            archived_at=c.archived_at,
        )


class ChannelPageOut(ApiModel):
    items: list[FreeChannelOut]
    next_before: int | None


class MembershipOut(ApiModel):
    channel: FreeChannelOut
    changed: bool


class LeaveOut(ApiModel):
    """Own cleanup receipt only, including when former scope access was revoked."""

    channel_id: UUID
    changed: bool
    membership: Literal["ABSENT"] = "ABSENT"


class CreatedChannelOut(ApiModel):
    channel: FreeChannelOut
    replayed: bool


class OfficialRequestOut(ApiModel):
    id: UUID
    channel_id: UUID
    status: RequestStatus
    review_state: Literal["BLOCKED_APPROVER_POLICY"] = REVIEW_BLOCKED
    reason: str
    revision: int
    created_at: AwareDatetime
    updated_at: AwareDatetime

    @classmethod
    def of(cls, row: OfficialChannelRequest) -> Self:
        return cls(
            id=row.id,
            channel_id=row.channel_id,
            status=row.status,
            reason=row.reason,
            revision=row.revision,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )


class CreatedRequestOut(ApiModel):
    request: OfficialRequestOut
    replayed: bool


class RequestPageOut(ApiModel):
    items: list[OfficialRequestOut]
    next_before: int | None
