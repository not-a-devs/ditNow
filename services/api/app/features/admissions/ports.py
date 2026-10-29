from contextlib import AbstractContextManager
from typing import Protocol
from uuid import UUID

from app.features.admissions.models import (
    AdmissionGuide,
    ApplicantGrant,
    ApplicationRecord,
    DemoAdmissionPolicy,
)


class AdmissionTransaction(Protocol):
    """Single actor-scoped transaction, not a production DB/security implementation.

    Re-read current identity/applicant grant/policies; lock the actor/cycle and selected row.
    Atomic writes enforce owner+parent cycle+expected revision, policy windows, count limits
    and an idempotency ledger UNIQUE(actor, operation-with-resource, key). Same scope with a
    different canonical hash is 409. Persist ledger+row+minimal event together; roll back all
    on failure. Replay must retain tombstones and never recreate deleted records. Keep replay
    and audit access separated from public guide readers; do not log raw payloads/identity.
    Member/role assignment, received updates and operations with real documents are NOT enabled.
    """

    grant: ApplicantGrant

    def policies(self) -> list[DemoAdmissionPolicy]: ...
    def policy(self, cycle_id: UUID) -> DemoAdmissionPolicy | None: ...
    def applications(self) -> list[ApplicationRecord]: ...
    def get(self, application_id: UUID) -> ApplicationRecord | None: ...
    def replay(self, operation: str, key: str, payload_hash: str) -> UUID | None: ...
    def create(
        self, row: ApplicationRecord, operation: str, key: str, payload_hash: str
    ) -> ApplicationRecord: ...
    def replace(
        self,
        row: ApplicationRecord,
        expected_revision: int,
        operation: str,
        key: str,
        payload_hash: str,
    ) -> ApplicationRecord: ...


class AdmissionsStore(Protocol):
    def guides(self, offset: int, limit: int) -> list[AdmissionGuide]: ...
    def transaction(self, user_id: UUID) -> AbstractContextManager[AdmissionTransaction]: ...
