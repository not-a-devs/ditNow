"""Collaboration domain rules (FR-COM-002/003/006/007).

Two identity zones never share identifiers or fields:

- Anonymous zone (FR-COM-002/003): comments, bookmarks, search and reports attach to the
  existing anonymous post IDs of the community feature. Responses never carry an author ID,
  real name, department or any per-thread alias that could be correlated across posts.
- Real-name zone (FR-COM-006/007): study/club groups and their team activity space show only
  the public activity display name.

Every limit below is a virtual demo design default, not an approved school policy.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from urllib.parse import urlsplit

from app.core.errors import ApiError
from app.schemas.common import ErrorCode

ANONYMOUS_DISPLAY_NAME = "익명"
PAGE_MAX = 50
COMMENT_MIN, COMMENT_MAX = 1, 1000
SEARCH_MIN, SEARCH_MAX = 2, 50
EXCERPT_MAX = 120
GROUP_NAME_MIN, GROUP_NAME_MAX = 2, 60
GROUP_DESCRIPTION_MAX = 1000
# Capacity counts the leader. Demo design default only.
GROUP_CAPACITY_MIN, GROUP_CAPACITY_MAX = 2, 30
SPACE_POST_MIN, SPACE_POST_MAX = 1, 2000
SOURCE_URL_MAX = 2048
# Join rules shown to users are this demo's defaults, never a school club regulation.
POLICY_BASIS = "DEMO_DESIGN_DEFAULT"


def require_aware_utc(value: datetime) -> datetime:
    """Server clocks and stored times must be timezone-aware; normalized to UTC."""
    if value.tzinfo is None or value.utcoffset() is None:
        raise ApiError(ErrorCode.INTERNAL)
    return value.astimezone(UTC)


@dataclass(frozen=True, slots=True)
class CollaborationActor:
    """Verified caller injected by the shared auth owner. Holds identity only, never roles."""

    user_id: str


@dataclass(frozen=True, slots=True)
class ParticipationGrant:
    """Community participation entitlement re-evaluated by the UOW inside its transaction.

    Derived from server-side role/membership data (e.g. an approved demo student). A revoked
    grant blocks every request, including idempotent replays.
    """

    active: bool


class CommentStatus(StrEnum):
    ACTIVE = "active"
    DELETED = "deleted"


class ReportTargetType(StrEnum):
    ANONYMOUS_POST = "anonymous_post"
    ANONYMOUS_COMMENT = "anonymous_comment"


class ReportReason(StrEnum):
    """Fixed reasons only. Free-text bodies are refused to avoid collecting sensitive data."""

    SPAM = "spam"
    ABUSE = "abuse"
    HATE = "hate"
    SEXUAL = "sexual"
    PRIVACY = "privacy"
    MISINFORMATION = "misinformation"
    OTHER = "other"


class ReportStatus(StrEnum):
    # Review/sanction states are BLOCKED until an operator policy is approved.
    SUBMITTED = "submitted"


class GroupKind(StrEnum):
    STUDY = "study"
    CLUB = "club"


class JoinMode(StrEnum):
    OPEN = "open"
    APPROVAL = "approval"


class GroupStatus(StrEnum):
    OPEN = "open"
    CLOSED = "closed"


class GroupRole(StrEnum):
    LEADER = "leader"
    MEMBER = "member"


class MembershipStatus(StrEnum):
    PENDING = "pending"
    ACTIVE = "active"
    REJECTED = "rejected"
    LEFT = "left"


class SpacePostStatus(StrEnum):
    ACTIVE = "active"
    DELETED = "deleted"


class GroupOrigin(StrEnum):
    MEMBER_CREATED = "member_created"
    CATALOG = "catalog"


class SourceKind(StrEnum):
    OFFICIAL_PUBLIC = "OFFICIAL_PUBLIC"
    DEMO = "DEMO"
    USER_DEMO = "USER_DEMO"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True, slots=True)
class SourceRef:
    kind: SourceKind
    url: str | None = None
    checked_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class GroupGrant:
    """Actor's current membership in one group, read by the UOW in the same transaction."""

    role: GroupRole | None
    active: bool

    @property
    def is_member(self) -> bool:
        return self.active and self.role is not None

    @property
    def is_leader(self) -> bool:
        return self.is_member and self.role is GroupRole.LEADER


NO_GROUP_GRANT = GroupGrant(role=None, active=False)


@dataclass(frozen=True, slots=True)
class CommentRecord:
    id: str
    post_id: str
    author_id: str
    body: str
    status: CommentStatus
    revision: int
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class BookmarkRecord:
    user_id: str
    post_id: str
    created_at: datetime


@dataclass(frozen=True, slots=True)
class ReportRecord:
    id: str
    reporter_id: str
    target_type: ReportTargetType
    target_id: str
    reason: ReportReason
    status: ReportStatus
    created_at: datetime


@dataclass(frozen=True, slots=True)
class GroupRecord:
    id: str
    kind: GroupKind
    name: str
    description: str
    join_mode: JoinMode
    capacity: int
    member_count: int
    status: GroupStatus
    origin: GroupOrigin
    source: SourceRef
    revision: int
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class MembershipRecord:
    id: str
    group_id: str
    user_id: str
    role: GroupRole
    status: MembershipStatus
    revision: int
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class SpacePostRecord:
    id: str
    group_id: str
    author_id: str
    body: str
    status: SpacePostStatus
    revision: int
    created_at: datetime
    updated_at: datetime


def has_open_seat(group: GroupRecord) -> bool:
    return group.member_count < group.capacity


def is_safe_public_url(value: str | None) -> bool:
    """https only, with a host and without credentials, control characters or fragments."""
    if not value or len(value) > SOURCE_URL_MAX:
        return False
    if any(ord(char) < 0x21 or 0x7F <= ord(char) <= 0x9F for char in value):
        return False
    try:
        parts = urlsplit(value)
        _ = parts.port  # raises on a malformed port
    except ValueError:
        return False
    return (
        parts.scheme == "https"
        and bool(parts.hostname)
        and parts.username is None
        and parts.password is None
        and not parts.fragment
    )


def normalize_source(source: SourceRef, now: datetime) -> SourceRef:
    """Fail-closed provenance: an OFFICIAL_PUBLIC claim needs a safe URL and a past check date.

    Anything else (missing/unsafe URL, naive or future date) is downgraded to UNKNOWN without a
    link. Non-official kinds never carry a link or check date, so DEMO, USER_DEMO and UNKNOWN
    stay distinguishable from verified public sources.
    """
    if source.kind is SourceKind.OFFICIAL_PUBLIC:
        checked = source.checked_at
        if (
            is_safe_public_url(source.url)
            and checked is not None
            and checked.tzinfo is not None
            and checked.utcoffset() is not None
            and checked <= now
        ):
            return SourceRef(SourceKind.OFFICIAL_PUBLIC, source.url, checked.astimezone(UTC))
        return SourceRef(SourceKind.UNKNOWN)
    return SourceRef(source.kind)


def excerpt(body: str) -> str:
    text = " ".join(body.split())
    return text if len(text) <= EXCERPT_MAX else text[: EXCERPT_MAX - 1] + "…"
