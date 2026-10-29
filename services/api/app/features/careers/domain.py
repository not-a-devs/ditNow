"""Pure careers rules (FR-JOB-001~004, FR-OPP-005~006 first pass).

Everything here is a virtual demo boundary. No rule in this module is a DIT business rule:
unconfirmed rules are supplied through an explicitly injected `DemoCareerPolicy`, and the
school-policy path (real review, employment confirmation, counselling) stays BLOCKED.
"""

import re
import unicodedata
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Literal
from urllib.parse import urlsplit
from uuid import UUID

from app.core.errors import ApiError
from app.schemas.common import ErrorCode


class CareerGrant(StrEnum):
    """Capabilities read from the current unit of work, never from the client."""

    PROFILE_SELF = "career.profile.self"
    PROGRAM_APPLY_SELF = "career.program.apply.self"
    # Not an employer role: only lets a server-approved account keep private drafts.
    EMPLOYER_DRAFT = "career.employer_request.draft"


@dataclass(frozen=True, slots=True)
class CareersActor:
    """Server-verified caller supplied by the shared auth owner (not merged yet)."""

    user_id: UUID


class Provenance(StrEnum):
    # OFFICIAL_PUBLIC only when a safe original URL AND an aware checked date both exist.
    OFFICIAL_PUBLIC = "OFFICIAL_PUBLIC"
    DEMO = "DEMO"
    # Claimed official but missing URL/date: never shown as official.
    UNKNOWN = "UNKNOWN"


class ApplicationStatus(StrEnum):
    APPLIED = "applied"
    CANCELLED = "cancelled"


class EmploymentType(StrEnum):
    FULL_TIME = "full_time"
    PART_TIME = "part_time"
    INTERNSHIP = "internship"
    CONTRACT = "contract"


@dataclass(frozen=True, slots=True)
class DemoCareerPolicy:
    """Explicit demo values for rules the school has not confirmed. Not a DIT policy.

    There is no default instance: the router returns 503 until root injects one, so a demo
    value can never silently become the school rule.
    """

    policy_id: str
    max_active_applications_per_user: int
    enforce_program_window: bool
    allow_cancel_after_window: bool
    link_closed_contests: bool
    max_employer_drafts_per_actor: int
    basis: Literal["DEMO"] = "DEMO"

    def __post_init__(self) -> None:
        if self.basis != "DEMO":
            raise ValueError("careers policy must be labelled DEMO")
        if not re.fullmatch(r"[a-z0-9][a-z0-9._-]{2,63}", self.policy_id):
            raise ValueError("invalid policy_id")
        if not 1 <= self.max_active_applications_per_user <= 20:
            raise ValueError("max_active_applications_per_user out of range")
        if not 1 <= self.max_employer_drafts_per_actor <= 50:
            raise ValueError("max_employer_drafts_per_actor out of range")


def require_actor(actor: CareersActor | None) -> CareersActor:
    if actor is None:
        raise ApiError(ErrorCode.UNAUTHORIZED)
    return actor


def require_grant(grants: frozenset[CareerGrant], needed: CareerGrant) -> None:
    if needed not in grants:
        raise ApiError(ErrorCode.FORBIDDEN)


def ensure_utc(value: datetime | None) -> datetime | None:
    """Aware datetimes are normalised to UTC; naive values are rejected (adapter bug)."""
    if value is None:
        return None
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("naive datetime")
    return value.astimezone(UTC)


def safe_external_url(value: str | None) -> str | None:
    """Only absolute https URLs without credentials/controls leave the API."""
    if not value or len(value) > 2048:
        return None
    if any(unicodedata.category(c) in {"Cc", "Cf", "Zs", "Zl", "Zp"} for c in value):
        return None
    try:
        parts = urlsplit(value)
        port = parts.port
    except ValueError:
        return None
    if parts.scheme != "https" or not parts.hostname or parts.username or parts.password:
        return None
    if port is not None and port != 443:
        return None
    return value


def resolve_provenance(
    declared_official: bool, url: str | None, checked_at: datetime | None
) -> Provenance:
    if not declared_official:
        return Provenance.DEMO
    if safe_external_url(url) is None or checked_at is None or checked_at.tzinfo is None:
        return Provenance.UNKNOWN
    return Provenance.OFFICIAL_PUBLIC


# ---- private-text screening (virtual alias + skills only) ----

_EMAIL = re.compile(r"[^\s@]+@[^\s@]+\.[^\s@]+")
_LINK = re.compile(r"(?i)(?:https?://|www\.|[a-z0-9-]+\.(?:com|net|kr|org)\b)")
# Technology names that look like domains. Only these exact tokens are exempted from _LINK;
# any other `name.net` (and every URL/e-mail) is still refused.
_TECH_DOTNET = re.compile(r"(?i)(?<![\w.-])(?:asp|ado|vb)\.net(?![\w-]|\.\w)")
# Phone/ID-like runs: 9+ digits allowing common separators (010-1234-5678, 900101-1234567).
_DIGIT_RUN = re.compile(r"(?:\d[\s.\-()]*){9,}")
# A run made only of year.month[.day] dates (optionally a range) is a period, not a number.
_DATE = r"(?:19|20)\d{2}[.\-/](?:0?[1-9]|1[0-2])(?:[.\-/](?:0?[1-9]|[12]\d|3[01]))?\.?"
_PERIOD = re.compile(rf"{_DATE}(?:\s*-\s*{_DATE})?")


def reject_contact_details(value: str) -> str:
    """Refuse e-mail, links and phone/ID-like numbers. Pattern screening, not a guarantee: it
    cannot detect real names or every contact format, so the UI and docs state that only a
    virtual alias is allowed."""
    if _EMAIL.search(value) or _LINK.search(_TECH_DOTNET.sub(" ", value)):
        raise ValueError("contact details are not allowed")
    for run in _DIGIT_RUN.finditer(value):
        if not _PERIOD.fullmatch(run.group().strip(" \t\r\n()-")):
            raise ValueError("contact details are not allowed")
    return value


def reject_controls(value: str) -> str:
    for char in value:
        if unicodedata.category(char) in {"Cc", "Cf", "Cs", "Co"} and char not in "\n":
            raise ValueError("control characters are not allowed")
    return value


def window_open(starts: datetime | None, ends: datetime | None, now: datetime) -> bool:
    if starts is not None and now < starts:
        return False
    return not (ends is not None and now >= ends)
