"""Persistence contracts for API-JOB (first pass). No production adapter lives here.

The DB owner implements `CareersUnitOfWork` against MariaDB; until then the router fails closed
(503). The in-memory fake in tests only simulates this contract and proves nothing about real
InnoDB isolation.

Transaction contract (`with uow.transaction() as tx:` = one DB transaction):
- Everything read and written inside the block commits together or not at all. An exception
  leaving the block rolls back every write made in it.
- `grants()` is read inside the same transaction as the write it authorises, so a replay or a
  late write is checked against the *current* grant, not one cached at login.
- `put_claim` is UNIQUE on the full `ClaimScope` (actor, method, canonical path, key). A
  duplicate raises `StoreConflict`; the caller retries in a new transaction and replays.
- Claims are never deleted by resource deletes. A claim whose resource is gone is a tombstone:
  a late retry of the original create gets 409 instead of resurrecting the resource.
- `lock_program` must serialise concurrent applications for one program (e.g. SELECT ... FOR
  UPDATE on the program row) so capacity and per-user limits cannot be exceeded.
- `update_*`/`delete_*` are conditional on `expected_revision` (CAS) and return False when the
  row changed or vanished.
- UNIQUE(user_id) on profiles and UNIQUE(user_id, program_id) for *active* applications raise
  `StoreConflict` on violation.
"""

from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol
from uuid import UUID

from app.features.careers.domain import ApplicationStatus, CareerGrant, EmploymentType


class StoreConflict(Exception):
    """UNIQUE/CHECK violation reported by the adapter (mapped to 409 or replay)."""


ResourceType = Literal["profile", "program_application", "employer_request"]


@dataclass(frozen=True, slots=True)
class ClaimScope:
    actor_id: UUID
    method: Literal["POST"]
    canonical_path: str
    key: str


@dataclass(frozen=True, slots=True)
class IdempotencyClaim:
    scope: ClaimScope
    payload_hash: str
    resource_type: ResourceType
    resource_id: UUID


@dataclass(frozen=True, slots=True)
class ProfileRecord:
    id: UUID
    user_id: UUID
    alias: str
    desired_roles: tuple[str, ...]
    skills: tuple[str, ...]
    summary: str
    revision: int
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class ProgramRecord:
    """Career program row. `official` + URL + checked_at decide provenance."""

    id: UUID
    title: str
    host: str
    summary: str
    official: bool
    published: bool
    capacity: int | None = None
    apply_starts_at: datetime | None = None
    apply_ends_at: datetime | None = None
    source_url: str | None = None
    checked_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class ApplicationRecord:
    id: UUID
    user_id: UUID
    program_id: UUID
    status: ApplicationStatus
    note: str
    revision: int
    created_at: datetime
    updated_at: datetime
    cancelled_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class EmployerDraftRecord:
    id: UUID
    owner_id: UUID
    company_alias: str
    role_title: str
    description: str
    employment_type: EmploymentType
    closes_at: datetime
    revision: int
    created_at: datetime
    updated_at: datetime


class CareersTransaction(Protocol):
    # grants / idempotency
    def grants(self, user_id: UUID) -> frozenset[CareerGrant]: ...

    def find_claim(self, scope: ClaimScope) -> IdempotencyClaim | None: ...

    def put_claim(self, claim: IdempotencyClaim) -> None: ...

    # FR-JOB-002 profile (one per user)
    def get_profile(self, user_id: UUID) -> ProfileRecord | None: ...

    def get_profile_by_id(self, profile_id: UUID) -> ProfileRecord | None: ...

    def insert_profile(self, record: ProfileRecord) -> None: ...

    def update_profile(self, record: ProfileRecord, expected_revision: int) -> bool: ...

    def delete_profile(self, user_id: UUID, profile_id: UUID, expected_revision: int) -> bool: ...

    # FR-JOB-003 / FR-OPP-006 programs
    def list_programs(self) -> list[ProgramRecord]: ...

    def get_program(self, program_id: UUID) -> ProgramRecord | None: ...

    def lock_program(self, program_id: UUID) -> ProgramRecord | None: ...

    def count_active_for_program(self, program_id: UUID) -> int: ...

    def count_active_for_user(self, user_id: UUID) -> int: ...

    def find_active_application(
        self, user_id: UUID, program_id: UUID
    ) -> ApplicationRecord | None: ...

    def get_application(self, application_id: UUID) -> ApplicationRecord | None: ...

    def list_applications(self, user_id: UUID) -> list[ApplicationRecord]: ...

    def insert_application(self, record: ApplicationRecord) -> None: ...

    def update_application(self, record: ApplicationRecord, expected_revision: int) -> bool: ...

    # FR-JOB-004 employer request drafts
    def list_employer_drafts(self, owner_id: UUID) -> list[EmployerDraftRecord]: ...

    def get_employer_draft(self, draft_id: UUID) -> EmployerDraftRecord | None: ...

    def insert_employer_draft(self, record: EmployerDraftRecord) -> None: ...

    def update_employer_draft(
        self, record: EmployerDraftRecord, expected_revision: int
    ) -> bool: ...

    def delete_employer_draft(
        self, owner_id: UUID, draft_id: UUID, expected_revision: int
    ) -> bool: ...


class CareersUnitOfWork(Protocol):
    def transaction(self) -> AbstractContextManager[CareersTransaction]: ...
