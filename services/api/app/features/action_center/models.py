import unicodedata
from datetime import date
from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, Field, field_validator

from app.schemas.common import ApiModel


class SourceType(StrEnum):
    CLASS_SESSION = "CLASS_SESSION"
    TASK = "TASK"
    NOTICE = "NOTICE"
    OPPORTUNITY_DEADLINE = "OPPORTUNITY_DEADLINE"


# Fixed in-app section paths. Never built from client input or stored URLs; the source id is
# returned separately so the destination screen reloads the original under its own checks.
LINKS: dict[SourceType, str] = {
    SourceType.CLASS_SESSION: "/app/classrooms",
    SourceType.TASK: "/app/classrooms",
    SourceType.NOTICE: "/app/department",
    SourceType.OPPORTUNITY_DEADLINE: "/app/opportunities",
}

# DEMO = fictional record, OFFICIAL_PUBLIC = cited public snapshot, PLATFORM = authored inside
# this independent platform (not a school system record), UNKNOWN = provenance not provable.
RecordSource = Literal["DEMO", "OFFICIAL_PUBLIC", "PLATFORM", "UNKNOWN"]
SOURCE_LABELS: frozenset[str] = frozenset({"DEMO", "OFFICIAL_PUBLIC", "PLATFORM", "UNKNOWN"})


def single_line(value: str) -> str:
    if not value.strip() or any(unicodedata.category(c) in {"Cc", "Cf", "Cs"} for c in value):
        raise ValueError("Text must be a nonblank single line")
    return value.strip()


class SummaryItem(ApiModel):
    source_type: SourceType
    source_id: UUID
    title: str = Field(min_length=1, max_length=200)
    at: AwareDatetime
    link: str
    record_source: RecordSource


class HomeSummary(ApiModel):
    local_date: date
    utc_offset: Literal["+09:00"] = "+09:00"
    window_start: AwareDatetime
    window_end: AwareDatetime
    classes: list[SummaryItem] = Field(max_length=10)
    tasks: list[SummaryItem] = Field(max_length=10)
    notices: list[SummaryItem] = Field(max_length=10)
    deadlines: list[SummaryItem] = Field(max_length=10)
    unread_notifications: int = Field(ge=0)
    unread_capped: bool
    ordering: Literal["TIME_ASC_DEMO"] = "TIME_ASC_DEMO"
    priority_policy: Literal["NOT_DEFINED"] = "NOT_DEFINED"
    school_connection: Literal["NOT_CONNECTED"] = "NOT_CONNECTED"


class NotificationRecord(ApiModel):
    """Private ledger row. recipient_id never leaves the server."""

    id: UUID
    recipient_id: UUID
    source_type: SourceType
    source_id: UUID
    event_key: str
    title: str = Field(min_length=1, max_length=200)
    record_source: RecordSource
    created_at: AwareDatetime
    read_at: AwareDatetime | None = None
    revision: int = Field(ge=1)

    @property
    def dedupe_key(self) -> tuple[UUID, SourceType, UUID, str]:
        return (self.recipient_id, self.source_type, self.source_id, self.event_key)


class NotificationView(ApiModel):
    id: UUID
    source_type: SourceType
    source_id: UUID
    title: str
    link: str
    record_source: RecordSource
    created_at: AwareDatetime
    read_at: AwareDatetime | None
    revision: int
    delivery: Literal["IN_APP_ONLY"] = "IN_APP_ONLY"


class NotificationPage(ApiModel):
    items: list[NotificationView]
    offset: int
    limit: int
    # Rows hidden by current visibility still advance the cursor, so pages never repeat.
    next_offset: int | None


class ReadInput(ApiModel):
    expected_revision: int = Field(ge=1)


class NotificationEvent(ApiModel):
    """Trusted internal event (outbox consumer), never a request body."""

    recipient_id: UUID
    source_type: SourceType
    source_id: UUID
    event_key: str = Field(pattern=r"^[A-Za-z0-9._:-]{8,120}$")
    title: str = Field(min_length=1, max_length=200)
    record_source: RecordSource

    @field_validator("title")
    @classmethod
    def clean_title(cls, value: str) -> str:
        return single_line(value)
