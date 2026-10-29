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
- Lock order (deadlock avoidance): a write transaction takes at most one actor lock and then
  at most one program lock, always `lock_actor` -> `lock_program`, never the reverse. Every
  write that changes an actor-wide aggregate (profile create/delete, apply/cancel, employer
  draft create/delete) takes `lock_actor` before it reads claims, limits or counts.
- `lock_actor(user_id)` holds an exclusive lock on one existing per-actor row until commit
  (e.g. SELECT ... FOR UPDATE on the actor's user/aggregate row; the DB owner picks the row).
  It serialises one actor's concurrent writes across *different* programs, so the per-user
  active-application limit and the employer-draft limit cannot be raced.
- `lock_program(program_id)` holds an exclusive lock on the program row until commit so the
  capacity count cannot be raced by other actors.
- Visibility after a lock: `grants`, `find_claim`, `count_*`, `find_active_application`,
  `get_application` and `list_employer_drafts` called after `lock_actor`/`lock_program` must
  see the latest *committed* rows, not a snapshot taken before the lock was granted. Under
  MariaDB InnoDB's default REPEATABLE READ a plain SELECT reuses the snapshot of the first
  read in the transaction, so the adapter must either run these transactions at READ
  COMMITTED or issue those reads as locking reads (FOR UPDATE / LOCK IN SHARE MODE), which
  read the latest committed version. Which one is chosen, and the server's actual isolation
  setting, is the DB owner's decision and is not verified here.
- Error mapping: UNIQUE/CHECK violations (e.g. MariaDB 1062) raise `StoreConflict`; deadlock
  and lock-wait timeout (e.g. 1213, 1205) raise `StoreBusy` after the adapter has rolled the
  transaction back. Neither carries the driver message; the service retries a bounded number
  of times in a *new* transaction and otherwise answers 409 without detail.
- `update_*`/`delete_*` are conditional on `expected_revision` (CAS) and return False when the
  row changed or vanished.
- UNIQUE(user_id) on profiles and UNIQUE(user_id, program_id) for *active* applications raise
  `StoreConflict` on violation. MariaDB has no partial/filtered index, so "UNIQUE only while
  status='applied'" cannot be declared directly; one option is a generated column such as
  `IF(status='applied', program_id, NULL)` plus UNIQUE(user_id, that column) (NULLs do not
  collide). The concrete schema is an open task for the DB owner, not decided here.
"""

from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol
from uuid import UUID

from app.features.careers.domain import ApplicationStatus, CareerGrant, EmploymentType


class StoreConflict(Exception):
    """UNIQUE/CHECK violation reported by the adapter (mapped to 409 or replay)."""


class StoreBusy(Exception):
    """Deadlock or lock-wait timeout; the transaction was rolled back and may be retried."""


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

    # serialisation (see module docstring for order and visibility)
    def lock_actor(self, user_id: UUID) -> None: ...

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
