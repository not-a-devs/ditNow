"""Persistence contracts for API-OPP.

The platform DB/auth owners implement these Protocols. No production adapter exists in this
feature package; the router fails closed (503) until one is injected.

Atomicity contract (one DB transaction per call, MariaDB InnoDB in the target design):
- `compare_and_set` updates the saved row only when its revision matches AND appends the status
  event in the same transaction. If the event insert fails, the row update must roll back and the
  error must propagate (no state change without its audit record).
- `insert_check` inserts the idempotency entry (UNIQUE on the full `IdempotencyScope`) and the
  check row together. If the scope already exists, nothing is inserted and the existing entry is
  returned. A UNIQUE(saved_id, sort_order) violation raises `StoreConflict`.
- Idempotency entries are never removed by `delete_check` or `delete_with_checks`; they become
  tombstones (`check is None`) so a replayed request cannot resurrect a deleted item.
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

# Shared provenance contract (docs/v1-draft/05_DB_API.md: OFFICIAL_PUBLIC/DEMO/USER_DEMO) plus
# the lowercase values proposed in docs/research/07_DATA_PROVENANCE_AND_SEEDS.md. USER_DEMO is
# user-created demo content and is never valid for the admin-approved opportunity catalog.
_SOURCE_KIND_FROM_STORAGE: dict[str, SourceKind] = {
    "OFFICIAL_PUBLIC": SourceKind.OFFICIAL_PUBLIC,
    "official_public": SourceKind.OFFICIAL_PUBLIC,
    "DEMO": SourceKind.DEMO,
    "synthetic_demo": SourceKind.DEMO,
}


def source_kind_from_storage(value: str) -> SourceKind:
    """Adapter helper: map a stored provenance value; unknown or USER_DEMO raises ValueError."""
    try:
        return _SOURCE_KIND_FROM_STORAGE[value]
    except KeyError:
        raise ValueError("unsupported opportunity source_kind") from None


class StoreConflict(Exception):
    """Raised by adapters when a UNIQUE/CHECK constraint rejects a write (mapped to 409)."""


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


@dataclass(frozen=True)
class IdempotencyScope:
    """Replay key bound to the verified actor, the parent path and the operation."""

    user_id: UUID
    opportunity_id: UUID
    operation: str
    key: str


@dataclass(frozen=True)
class IdempotencyEntry:
    scope: IdempotencyScope
    request_hash: str
    check_id: UUID
    # None once the created check was deleted (tombstone; the key stays consumed).
    check: CheckRecord | None


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

    def compare_and_set(
        self, record: SavedRecord, expected_revision: int, event: StatusEvent | None
    ) -> bool:
        """One transaction: conditional UPDATE + optional event INSERT; all-or-nothing."""
        ...

    def delete_with_checks(self, user_id: UUID, saved_id: UUID, expected_revision: int) -> bool:
        """One transaction; keeps idempotency entries as tombstones."""
        ...

    def list_checks(self, saved_id: UUID) -> list[CheckRecord]: ...

    def find_idempotency(self, scope: IdempotencyScope) -> IdempotencyEntry | None: ...

    def insert_check(
        self, record: CheckRecord, scope: IdempotencyScope, request_hash: str
    ) -> IdempotencyEntry:
        """One transaction; returns the existing entry unchanged when the scope already exists."""
        ...

    def compare_and_set_check(self, record: CheckRecord, expected_revision: int) -> bool: ...

    def delete_check(self, saved_id: UUID, check_id: UUID, expected_revision: int) -> bool:
        """Conditional DELETE; keeps the idempotency entry as a tombstone."""
        ...
