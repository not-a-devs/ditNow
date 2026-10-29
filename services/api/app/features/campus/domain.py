"""Campus communication domain records (FR-DEPT-001/002/005, FR-NOT-001/002, FR-ACA-001).

These are storage-agnostic values. No persistence adapter exists yet; the shared DB owner
implements the repository protocols in ``repositories.py``.
"""

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import StrEnum
from uuid import UUID

MIN_GRADE = 1
# Input sanity bound only. Access is decided by server-resolved memberships, not this number.
MAX_GRADE = 6


class AudienceType(StrEnum):
    SCHOOL = "SCHOOL"
    DEPARTMENT = "DEPARTMENT"
    DEPARTMENT_GRADE = "DEPARTMENT_GRADE"


@dataclass(frozen=True, slots=True)
class Audience:
    type: AudienceType
    department_id: UUID | None = None
    grade: int | None = None

    def __post_init__(self) -> None:
        if self.type is AudienceType.SCHOOL:
            if self.department_id is not None or self.grade is not None:
                raise ValueError("school audience has no department or grade")
        elif self.type is AudienceType.DEPARTMENT:
            if self.department_id is None or self.grade is not None:
                raise ValueError("department audience requires only department_id")
        else:
            if self.department_id is None or self.grade is None:
                raise ValueError("department grade audience requires department_id and grade")
            if not MIN_GRADE <= self.grade <= MAX_GRADE:
                raise ValueError("grade out of range")


@dataclass(frozen=True, slots=True)
class Membership:
    """A currently approved academic membership. Expired/pending rows must not be passed in."""

    department_id: UUID
    grade: int | None = None


@dataclass(frozen=True, slots=True)
class CampusActor:
    """Server-resolved identity. Never build this from client-supplied role/department claims."""

    user_id: UUID
    memberships: tuple[Membership, ...] = ()
    # Exact audiences this actor may author official notices for, derived by the shared
    # auth layer from approved role_assignments. Empty for ordinary students.
    notice_author_scopes: frozenset[Audience] = field(default_factory=frozenset)


class ChannelKind(StrEnum):
    DEPARTMENT_ALL = "DEPARTMENT_ALL"
    DEPARTMENT_GRADE = "DEPARTMENT_GRADE"


@dataclass(frozen=True, slots=True)
class Channel:
    id: UUID
    department_id: UUID
    kind: ChannelKind
    name: str
    grade: int | None = None


class MessageKind(StrEnum):
    TEXT = "TEXT"
    NOTICE_CARD = "NOTICE_CARD"


@dataclass(frozen=True, slots=True)
class ChatMessage:
    id: UUID
    channel_id: UUID
    seq: int
    kind: MessageKind
    created_at: datetime
    author_id: UUID | None = None
    body: str | None = None
    client_nonce: str | None = None
    reference_notice_id: UUID | None = None


class NoticeStatus(StrEnum):
    DRAFT = "DRAFT"
    PUBLISHED = "PUBLISHED"
    ARCHIVED = "ARCHIVED"


@dataclass(frozen=True, slots=True)
class Notice:
    id: UUID
    audience: Audience
    title: str
    body: str
    status: NoticeStatus
    revision: int
    author_id: UUID
    created_at: datetime
    updated_at: datetime
    published_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class DeliveryTarget:
    department_id: UUID
    grade: int | None


@dataclass(frozen=True, slots=True)
class DeliveryResult:
    channel_ids: tuple[UUID, ...]
    created_count: int
    missing_targets: tuple[DeliveryTarget, ...]


class SourceKind(StrEnum):
    OFFICIAL_PUBLIC = "OFFICIAL_PUBLIC"
    DEMO = "DEMO"


@dataclass(frozen=True, slots=True)
class AcademicTerm:
    id: UUID
    name: str
    starts_on: date
    ends_on: date
    source_kind: SourceKind


@dataclass(frozen=True, slots=True)
class AcademicEvent:
    id: UUID
    term_id: UUID
    title: str
    starts_on: date
    ends_on: date
    source_kind: SourceKind
    source_url: str | None = None
    checked_at: date | None = None
