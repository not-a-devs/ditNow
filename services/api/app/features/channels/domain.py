"""Student free channels and official-channel requests (FR-DEPT-003/004, first pass).

Storage-agnostic records. Scope and eligibility reuse the campus membership contract
(``app.features.campus``): a free channel lives in one department, optionally narrowed to one
grade, exactly like the authoritative default channels. Free channels are a separate ledger;
default department/grade channels are never created, edited or archived here.
"""

import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from app.core.errors import ApiError
from app.features.campus import policy as campus_policy
from app.features.campus.domain import CampusActor, Channel, ChannelKind, Membership
from app.features.campus.services import clean_text
from app.schemas.common import ErrorCode

# Design defaults (not school policy); see docs/dev-prep/TASK_CHANNELS_IMPLEMENTATION.md.
NAME_MAX_LENGTH = 40
DESCRIPTION_MAX_LENGTH = 500
REASON_MIN_LENGTH = 10
REASON_MAX_LENGTH = 1000
PAGE_MAX = 50
MEMBER_LIMIT = 300
OWNED_ACTIVE_LIMIT_PER_SCOPE = 5

# Approval/badge granting has no approved approver role yet (FR-DEPT-004, DEC-007). Every
# request response carries this marker so no client can read PENDING as "under review".
REVIEW_BLOCKED = "BLOCKED_APPROVER_POLICY"

_SPACES = re.compile(r"\s+")


class ChannelStatus(StrEnum):
    ACTIVE = "ACTIVE"
    ARCHIVED = "ARCHIVED"


class MemberRole(StrEnum):
    OWNER = "OWNER"
    MEMBER = "MEMBER"


class RequestStatus(StrEnum):
    PENDING = "PENDING"
    # Set only by the system when the owner archives the channel. No approve/reject exists.
    CANCELLED = "CANCELLED"


@dataclass(frozen=True, slots=True)
class ChannelsActor:
    """Verified identity only. Memberships are re-read inside each unit of work."""

    user_id: UUID


@dataclass(frozen=True, slots=True)
class FreeChannel:
    id: UUID
    department_id: UUID
    grade: int | None
    name: str
    name_key: str
    description: str
    owner_id: UUID
    status: ChannelStatus
    # Bumped only by owner edits/archive; membership changes never invalidate an owner's CAS.
    revision: int
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None = None
    # Maintained by the store inside the membership write transaction.
    member_count: int = 0
    # Store-assigned monotonic order for cursor pagination (0 before insert).
    seq: int = 0


@dataclass(frozen=True, slots=True)
class ChannelMembership:
    channel_id: UUID
    user_id: UUID
    role: MemberRole
    joined_at: datetime


@dataclass(frozen=True, slots=True)
class OfficialChannelRequest:
    id: UUID
    channel_id: UUID
    requester_id: UUID
    reason: str
    status: RequestStatus
    revision: int
    created_at: datetime
    updated_at: datetime
    seq: int = 0


def in_scope(
    user_id: UUID, memberships: tuple[Membership, ...], department_id: UUID, grade: int | None
) -> bool:
    """Same rule as the authoritative default channels (campus ``can_access_channel``)."""
    kind = ChannelKind.DEPARTMENT_ALL if grade is None else ChannelKind.DEPARTMENT_GRADE
    probe = Channel(id=department_id, department_id=department_id, kind=kind, name="", grade=grade)
    return campus_policy.can_access_channel(CampusActor(user_id, memberships), probe)


def channel_name(value: str) -> tuple[str, str]:
    """Return (display name, uniqueness key). NFC display, NFKC+casefold collapsed key."""
    text = clean_text(unicodedata.normalize("NFC", value), NAME_MAX_LENGTH, multiline=False)
    text = _SPACES.sub(" ", text)
    key = _SPACES.sub(" ", unicodedata.normalize("NFKC", text).casefold()).strip()
    if not key:
        raise ApiError(ErrorCode.VALIDATION)
    return text, key


def description_text(value: str) -> str:
    text = unicodedata.normalize("NFC", value)
    if not text.strip():
        return ""
    return clean_text(text, DESCRIPTION_MAX_LENGTH, multiline=True)


def reason_text(value: str) -> str:
    text = clean_text(unicodedata.normalize("NFC", value), REASON_MAX_LENGTH, multiline=True)
    if len(text) < REASON_MIN_LENGTH:
        raise ApiError(ErrorCode.VALIDATION)
    return text
