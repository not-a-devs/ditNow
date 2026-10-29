from contextlib import AbstractContextManager
from typing import Protocol
from uuid import UUID

from app.features.student_life.models import (
    DemoBadgeRecord,
    DemoLifePolicy,
    LifeGrant,
    LifeRequestRecord,
    PublicLifeGuide,
)


class LifeTransaction(Protocol):
    """Future adapter: one transaction re-reads current identity/program grant and policies.

    Lock actor+program+request for all counts, windows, owner/parent checks and CAS. Writes
    atomically commit row+minimal event+replay ledger UNIQUE(actor, operation/resource, key)
    with canonical body hash; changed hash conflicts. Preserve replay tombstones and recheck
    current permissions on every replay/cancel. Never store a sensitive support body, real
    identity form or badge signature. Staff reply/assignment/issue authority is NOT enabled.
    Lists are scoped/bounded; capacity is an explicitly injected fictional request limit.
    Test fake locking/rollback is not proof of MariaDB isolation, privileges or persistence.
    """

    grant: LifeGrant

    def policies(self) -> list[DemoLifePolicy] | None: ...
    def policy(self, program_id: UUID) -> DemoLifePolicy | None: ...
    def requests(self) -> list[LifeRequestRecord]: ...
    def program_count(self, program_id: UUID) -> int: ...
    def badges(self) -> list[DemoBadgeRecord]: ...
    def get(self, id: UUID) -> LifeRequestRecord | None: ...
    def replay(self, operation: str, key: str, body_hash: str) -> UUID | None: ...
    def create(
        self, row: LifeRequestRecord, operation: str, key: str, body_hash: str
    ) -> LifeRequestRecord: ...
    def replace(
        self,
        row: LifeRequestRecord,
        expected_revision: int,
        operation: str,
        key: str,
        body_hash: str,
    ) -> LifeRequestRecord: ...


class LifeStore(Protocol):
    def guides(self, offset: int, limit: int) -> list[PublicLifeGuide]: ...
    def transaction(self, user_id: UUID) -> AbstractContextManager[LifeTransaction]: ...
