"""Inactive contracts, not MariaDB implementations or auth/session issuance.

The DB owner must bind unit_of_work to a verified common principal, lock its existing
identity row, and read current active DEMO identity/roles/memberships in that same transaction.
No token-cached department is authoritative. Lock order: actor -> question -> item/claim.
lock_question must lock even a missing/deleted parent namespace until commit; comment writes
and question deletion use the same lock. Reads use a consistent snapshot and current access.
Rows and claims commit together; every exception rolls back all writes. Claim namespace is
UNIQUE(actor_id, canonical path, key), with exact case-sensitive keys/digests. CAS updates
must condition id, owner, department, ACTIVE and revision and reject conflicts, not overwrite.
Deleted items/claims remain tombstones. Never provision a second identity or notice ledger.
Question/comment queries must explicitly filter source_kind=DEMO and ACTIVE before stable
(created_at,id) pagination. Private Item requires that source, not an inferred display default.

The existing campus NoticeRepository is a read-only port in this module. The supplied instance
MUST share this UOW/connection. Current notice + revision metadata/attachments use one snapshot;
metadata must be restricted to that notice/current revision. Do not expose draft history text,
author IDs, storage paths, signed URLs or unapproved file access. Metadata carries no download.
No content body, personal identity, keys, SQL parameters or attachment paths may enter logs.
"""

from collections.abc import Sequence
from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from app.features.campus.domain import CampusActor
from app.features.campus.repositories import NoticeRepository
from app.features.notice_discussion.models import (
    AttachmentMetadata,
    Claim,
    Item,
    RevisionMetadata,
)


@dataclass(frozen=True)
class CurrentAccess:
    actor: CampusActor
    active: bool
    demo: bool
    student_departments: frozenset[UUID]


class UnitOfWork(Protocol):
    notices: NoticeRepository

    def current_access(self) -> CurrentAccess | None: ...

    def notice_attachments(
        self, notice_id: UUID, revision: int
    ) -> Sequence[AttachmentMetadata]: ...

    def notice_history(self, notice_id: UUID, revision: int) -> Sequence[RevisionMetadata]: ...

    def lock_question(self, question_id: UUID) -> None: ...

    def get(self, item_id: UUID) -> Item | None: ...

    def list_questions(self, department_id: UUID, offset: int, limit: int) -> Sequence[Item]: ...

    def list_comments(self, question_id: UUID, offset: int, limit: int) -> Sequence[Item]: ...

    def find_claim(self, namespace: tuple[UUID, str, str]) -> Claim | None: ...

    def insert(self, item: Item, claim: Claim) -> None: ...

    def compare_and_set(self, item: Item, expected_revision: int) -> None: ...


class Store(Protocol):
    def unit_of_work(self, actor_id: UUID) -> AbstractContextManager[UnitOfWork]: ...
