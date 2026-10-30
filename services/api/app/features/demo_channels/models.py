from datetime import datetime
from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, StrictBool, field_validator

from app.schemas.common import ApiModel

PER_USER_MAX = 20
GLOBAL_MAX = 200


class Purpose(StrEnum):
    STUDY = "study"
    PROJECT = "project"
    SOCIAL = "social"


class RequestedKind(StrEnum):
    FREE = "FREE"
    OFFICIAL = "OFFICIAL"


class RequestStatus(StrEnum):
    CREATED = "CREATED"
    PENDING_REVIEW = "PENDING_REVIEW"


# Fixed generated titles: the client never supplies free text.
PURPOSE_LABELS = {
    Purpose.STUDY: "스터디",
    Purpose.PROJECT: "프로젝트",
    Purpose.SOCIAL: "친목",
}
KIND_LABELS = {
    RequestedKind.FREE: "자유 채널(가상)",
    RequestedKind.OFFICIAL: "공식 채널 신청(가상·실제 검토 없음)",
}


def generated_title(purpose: Purpose, kind: RequestedKind) -> str:
    return f"[DEMO] {PURPOSE_LABELS[purpose]} {KIND_LABELS[kind]}"


class DemoChannelRequestCreate(ApiModel):
    """Only these three fields are accepted; actor/department/role/title/status are rejected."""

    purpose: Purpose
    requested_kind: RequestedKind
    consent: StrictBool

    @field_validator("consent")
    @classmethod
    def consent_required(cls, value: bool) -> bool:
        if value is not True:
            raise ValueError("consent required")
        return value


class DemoChannelRequestView(ApiModel):
    id: UUID
    purpose: Purpose
    requested_kind: RequestedKind
    title: str
    status: RequestStatus
    revision: int
    created_at: AwareDatetime
    official_badge: Literal[False] = False
    real_review: Literal["NOT_OPERATED"] = "NOT_OPERATED"
    record_source: Literal["DEMO"] = "DEMO"
    persistence: Literal["PROCESS_MEMORY"] = "PROCESS_MEMORY"


class DemoChannelRequestList(ApiModel):
    items: list[DemoChannelRequestView]
    per_user_limit: int = PER_USER_MAX
    record_source: Literal["DEMO"] = "DEMO"
    persistence: Literal["PROCESS_MEMORY"] = "PROCESS_MEMORY"


class DemoChannelRequestCancelled(ApiModel):
    id: UUID
    cancelled: Literal[True] = True


class DemoChannelRecord(ApiModel):
    """Internal row; ``owner_id`` never leaves the store in a response."""

    id: UUID
    owner_id: UUID
    purpose: Purpose
    requested_kind: RequestedKind
    status: RequestStatus
    revision: int
    created_at: datetime

    def view(self) -> DemoChannelRequestView:
        return DemoChannelRequestView(
            id=self.id,
            purpose=self.purpose,
            requested_kind=self.requested_kind,
            title=generated_title(self.purpose, self.requested_kind),
            status=self.status,
            revision=self.revision,
            created_at=self.created_at,
        )
