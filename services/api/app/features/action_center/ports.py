"""Inactive contracts, not MariaDB implementations, auth/session issuance or push delivery.

The DB owner binds unit_of_work to a verified common principal and reads its current active
DEMO identity/memberships in that same transaction (the existing notice_discussion
``CurrentAccess`` shape is reused; no second identity ledger). Token-cached scopes are never
authoritative, so membership/enrollment revocation applies on the next read.

Original records stay in their existing ledgers. ``notices`` is the campus NoticeRepository (the
single notice authority) on the same connection; visibility is re-decided by campus.policy.
``sources`` is a provider-neutral read port that the integration owner implements by delegating
to the academics (enrollment/meeting), online_learning (due work) and opportunities (saved
deadline) ports for the bound actor only. It returns references (id/title/time/provenance),
never copies, and must not widen scope beyond what those modules would show the actor.

Notifications: UNIQUE(recipient_id, source_type, source_id, event_key) is the duplicate source
event constraint. ``insert_notification`` raises ApiError(CONFLICT) when that key already
exists. ``mark_read`` is a CAS: UPDATE ... SET read_at, revision=revision+1 WHERE id AND
recipient AND revision=expected AND read_at IS NULL; False when no row matched. Every list is
scoped to the bound recipient and ordered (created_at DESC, id DESC). Exceptions roll back all
writes. Titles, keys and ids never enter logs. The in-memory test fakes prove none of this.
"""

from collections.abc import Sequence
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from app.features.action_center.models import NotificationRecord, RecordSource, SourceType
from app.features.campus.repositories import NoticeRepository
from app.features.notice_discussion.ports import CurrentAccess


@dataclass(frozen=True)
class SourceRef:
    source_type: SourceType
    source_id: UUID
    title: str
    at: datetime
    record_source: RecordSource


class SourceReader(Protocol):
    def classes_between(self, start: datetime, end: datetime, limit: int) -> Sequence[SourceRef]:
        """Meetings of the actor's current ENROLLED offerings starting within [start, end)."""
        ...

    def tasks_due_between(
        self, start: datetime, end: datetime, limit: int
    ) -> Sequence[SourceRef]: ...

    def deadlines_between(
        self, start: datetime, end: datetime, limit: int
    ) -> Sequence[SourceRef]: ...

    def is_visible(self, source_type: SourceType, source_id: UUID) -> bool:
        """Current access of the actor to a non-notice original (revocation check)."""
        ...


class UnitOfWork(Protocol):
    notices: NoticeRepository
    sources: SourceReader

    def current_access(self) -> CurrentAccess | None: ...

    def list_notifications(self, offset: int, limit: int) -> Sequence[NotificationRecord]: ...

    def list_unread(self, limit: int) -> Sequence[NotificationRecord]: ...

    def get_notification(self, notification_id: UUID) -> NotificationRecord | None: ...

    def find_notification(
        self, dedupe_key: tuple[UUID, SourceType, UUID, str]
    ) -> NotificationRecord | None: ...

    def insert_notification(self, row: NotificationRecord) -> None: ...

    def mark_read(self, row: NotificationRecord, expected_revision: int) -> bool: ...


class Store(Protocol):
    def unit_of_work(self, actor_id: UUID) -> AbstractContextManager[UnitOfWork]: ...
