"""Persistence contracts for API-OPP.

The platform DB/auth owners implement these Protocols. No production adapter exists in this
feature package; the router fails closed (503) until one is injected.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol
from uuid import UUID

from app.features.opportunities.schemas import (
    OpportunityKind,
    PreparationStatus,
    PublicationStatus,
    SourceKind,
    SubmissionMode,
)


@dataclass(frozen=True)
class TargetScope:
    level: str = "school"
    department_codes: tuple[str, ...] = ()
    academic_years: tuple[int, ...] = ()


@dataclass(frozen=True)
class OpportunityFile:
    filename: str
    original_url: str | None
    checked_at: datetime | None = None


@dataclass(frozen=True)
class OpportunityRecord:
    id: UUID
    kind: OpportunityKind
    title: str
    organization: str
    eligibility: str
    submission_mode: SubmissionMode
    source_kind: SourceKind
    status: PublicationStatus
    target_scope: TargetScope = field(default_factory=TargetScope)
    apply_starts_at: datetime | None = None
    deadline_at: datetime | None = None
    destination: str | None = None
    original_url: str | None = None
    source_url: str | None = None
    checked_at: datetime | None = None
    files: tuple[OpportunityFile, ...] = ()


@dataclass(frozen=True)
class OpportunityQuery:
    kind: OpportunityKind | None = None
    text: str | None = None
    department_code: str | None = None
    open_only: bool = False
    limit: int = 20
    cursor: str | None = None


@dataclass(frozen=True)
class OpportunityPage:
    items: list[OpportunityRecord]
    next_cursor: str | None


@dataclass(frozen=True)
class SavedRecord:
    id: UUID
    user_id: UUID
    opportunity_id: UUID
    status: PreparationStatus
    memo: str
    self_reported_submitted_at: datetime | None
    revision: int
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class CheckRecord:
    id: UUID
    saved_id: UUID
    text: str
    sort_order: int
    completed_at: datetime | None
    revision: int


@dataclass(frozen=True)
class StatusEvent:
    saved_id: UUID
    user_id: UUID
    from_status: PreparationStatus
    to_status: PreparationStatus
    occurred_at: datetime
    correction: bool


class OpportunityCatalog(Protocol):
    """Read-only public projection. Must only return admin-approved records."""

    def list_public(self, query: OpportunityQuery, now: datetime) -> OpportunityPage: ...

    def get(self, opportunity_id: UUID) -> OpportunityRecord | None: ...


class SavedOpportunityStore(Protocol):
    """Owner-scoped storage. Every lookup is keyed by the verified user_id."""

    def get(self, user_id: UUID, opportunity_id: UUID) -> SavedRecord | None: ...

    def list_for_user(self, user_id: UUID) -> list[SavedRecord]: ...

    def insert_if_absent(self, record: SavedRecord) -> tuple[SavedRecord, bool]:
        """Atomic on UNIQUE(user_id, opportunity_id); returns (row, created)."""
        ...

    def compare_and_set(self, record: SavedRecord, expected_revision: int) -> bool: ...

    def delete_with_checks(self, user_id: UUID, saved_id: UUID, expected_revision: int) -> bool: ...

    def append_status_event(self, event: StatusEvent) -> None: ...

    def list_checks(self, saved_id: UUID) -> list[CheckRecord]: ...

    def find_check_by_idempotency_key(
        self, saved_id: UUID, key: str
    ) -> tuple[CheckRecord, str] | None: ...

    def insert_check(
        self, record: CheckRecord, idempotency_key: str, request_hash: str
    ) -> None: ...

    def compare_and_set_check(self, record: CheckRecord, expected_revision: int) -> bool: ...

    def delete_check(self, saved_id: UUID, check_id: UUID, expected_revision: int) -> bool: ...
