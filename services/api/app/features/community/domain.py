"""Pure community domain rules (FR-COM-001, FR-COM-004, FR-COM-005 capacity/state only).

Anonymous posts and real-name recruitments are separate aggregates. Nothing here links an
anonymous author to a recruitment owner or profile.
"""

from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum

from app.core.errors import ApiError
from app.schemas.common import ErrorCode

ANONYMOUS_DISPLAY_NAME = "익명"
TITLE_MIN, TITLE_MAX = 2, 120
BODY_MIN, BODY_MAX = 1, 5000
# Capacity counts the recruiter. 20 is a demo design default, not an approved policy value.
CAPACITY_MIN, CAPACITY_MAX = 2, 20
FIELD_MAX = 30
ROLE_MAX, ROLES_MAX = 30, 10
PAGE_MAX = 50


@dataclass(frozen=True, slots=True)
class CommunityActor:
    """Server-verified caller supplied by the (not yet merged) auth owner.

    ``community_access`` must come from server-side role/membership evaluation, never from
    client claims. ``user_id`` is an opaque internal identifier and is never returned by
    anonymous post responses.
    """

    user_id: str
    community_access: bool


class PostStatus(StrEnum):
    ACTIVE = "active"
    HIDDEN = "hidden"
    DELETED = "deleted"


class RecruitmentStatus(StrEnum):
    OPEN = "open"
    CLOSED = "closed"
    CANCELLED = "cancelled"


class ApplicationStatus(StrEnum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    WITHDRAWN = "withdrawn"


RECRUITMENT_TRANSITIONS: dict[RecruitmentStatus, frozenset[RecruitmentStatus]] = {
    RecruitmentStatus.OPEN: frozenset({RecruitmentStatus.CLOSED, RecruitmentStatus.CANCELLED}),
    RecruitmentStatus.CLOSED: frozenset(),
    RecruitmentStatus.CANCELLED: frozenset(),
}

APPLICATION_TRANSITIONS: dict[ApplicationStatus, frozenset[ApplicationStatus]] = {
    ApplicationStatus.PENDING: frozenset(
        {ApplicationStatus.ACCEPTED, ApplicationStatus.REJECTED, ApplicationStatus.WITHDRAWN}
    ),
    ApplicationStatus.ACCEPTED: frozenset(),
    ApplicationStatus.REJECTED: frozenset(),
    ApplicationStatus.WITHDRAWN: frozenset(),
}


@dataclass(frozen=True, slots=True)
class AnonymousPostPrivate:
    """Private ledger row (``anonymous_posts_private``). Server-internal only."""

    id: str
    author_id: str
    title: str
    body: str
    status: PostStatus
    revision: int
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class AnonymousPostPublicRow:
    """Public read model row (``anonymous_posts_public``); has no author field by design."""

    id: str
    title: str
    body: str
    status: PostStatus
    revision: int
    comment_count: int
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class Recruitment:
    id: str
    owner_id: str
    title: str
    body: str
    field: str
    roles: tuple[str, ...]
    capacity: int
    accepted_count: int
    deadline_at: datetime
    status: RecruitmentStatus
    opportunity_id: str | None
    revision: int
    created_at: datetime
    updated_at: datetime


def require_member(actor: CommunityActor | None) -> CommunityActor:
    if actor is None:
        raise ApiError(ErrorCode.UNAUTHORIZED)
    if not actor.community_access or not actor.user_id:
        raise ApiError(ErrorCode.FORBIDDEN)
    return actor


def team_size(accepted_count: int) -> int:
    """Capacity counts the recruiter, so the team is recruiter + accepted applicants."""
    return 1 + accepted_count


def has_open_seat(capacity: int, accepted_count: int) -> bool:
    return team_size(accepted_count) < capacity


def effective_status(recruitment: Recruitment, now: datetime) -> RecruitmentStatus:
    """Deadline is judged by server time; an expired open recruitment reads as closed."""
    if recruitment.status is RecruitmentStatus.OPEN and now >= recruitment.deadline_at:
        return RecruitmentStatus.CLOSED
    return recruitment.status


def transition_recruitment(
    recruitment: Recruitment, target: RecruitmentStatus, now: datetime
) -> Recruitment:
    if target not in RECRUITMENT_TRANSITIONS[recruitment.status]:
        raise ApiError(ErrorCode.CONFLICT)
    return replace(recruitment, status=target, revision=recruitment.revision + 1, updated_at=now)


def transition_application(current: ApplicationStatus, target: ApplicationStatus) -> None:
    if target not in APPLICATION_TRANSITIONS[current]:
        raise ApiError(ErrorCode.CONFLICT)


def check_accept(recruitment: Recruitment, now: datetime) -> None:
    """Pre-check for FR-COM-005 acceptance. The repository must re-run it under a row lock."""
    if effective_status(recruitment, now) is not RecruitmentStatus.OPEN:
        raise ApiError(ErrorCode.CONFLICT)
    if not has_open_seat(recruitment.capacity, recruitment.accepted_count):
        raise ApiError(ErrorCode.CONFLICT)


def check_application(recruitment: Recruitment, applicant_id: str, now: datetime) -> None:
    if applicant_id == recruitment.owner_id:
        raise ApiError(ErrorCode.CONFLICT)
    check_accept(recruitment, now)
