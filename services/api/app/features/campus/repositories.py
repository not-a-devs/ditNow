"""Storage protocols. No production implementation exists in this package.

The shared DB owner implements these against MariaDB with the unique constraints noted on
each method. In-memory fakes live only under ``tests/``.
"""

from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Protocol
from uuid import UUID

from fastapi import Request

from app.features.campus.domain import (
    AcademicEvent,
    AcademicTerm,
    Audience,
    CampusActor,
    Channel,
    ChatMessage,
    Notice,
    NoticeStatus,
)


class ActorResolver(Protocol):
    """Shared auth adapter: verify session and reload current memberships/roles from the DB."""

    def resolve(self, request: Request) -> CampusActor | None: ...


class ChannelRepository(Protocol):
    def get_channel(self, channel_id: UUID) -> Channel | None: ...

    def list_department_channels(self, department_id: UUID) -> Sequence[Channel]: ...

    # Unique default channel per (department_id, grade); grade None = department-wide.
    def find_default_channel(self, department_id: UUID, grade: int | None) -> Channel | None: ...


class MessageRepository(Protocol):
    # Atomic insert guarded by UNIQUE(channel_id, author_id, client_nonce).
    # Returns (stored message, created). On conflict returns the existing row, created=False.
    def insert_text(
        self,
        channel_id: UUID,
        author_id: UUID,
        body: str,
        client_nonce: str,
        created_at: datetime,
    ) -> tuple[ChatMessage, bool]: ...

    # Atomic insert guarded by UNIQUE(channel_id, reference_notice_id).
    def ensure_notice_card(
        self, channel_id: UUID, notice_id: UUID, created_at: datetime
    ) -> tuple[ChatMessage, bool]: ...

    # Newest first, seq strictly below ``before_seq`` when given.
    def list_messages(
        self, channel_id: UUID, before_seq: int | None, limit: int
    ) -> Sequence[ChatMessage]: ...


class NoticeRepository(Protocol):
    def get(self, notice_id: UUID) -> Notice | None: ...

    def get_many(self, notice_ids: Sequence[UUID]) -> Mapping[UUID, Notice]: ...

    def create(self, notice: Notice) -> Notice: ...

    # Single conditional UPDATE of title/body/updated_at with revision = expected_revision + 1,
    # WHERE id AND revision = expected_revision AND status = expected_status. Never writes
    # status, so a concurrent archive/publish cannot be overwritten. None when no row matched.
    def save_revision(
        self,
        notice_id: UUID,
        expected_revision: int,
        expected_status: NoticeStatus,
        title: str,
        body: str,
        at: datetime,
    ) -> Notice | None: ...

    # Single conditional UPDATE of status (and published_at when publishing)
    # WHERE id AND status = from_status AND revision = expected_revision.
    # None when another writer changed status or content first.
    def transition(
        self,
        notice_id: UUID,
        from_status: NoticeStatus,
        to_status: NoticeStatus,
        expected_revision: int,
        at: datetime,
    ) -> Notice | None: ...

    # Only PUBLISHED/ARCHIVED rows whose audience is in ``audiences``; newest first.
    def list_released_for(self, audiences: Sequence[Audience], limit: int) -> Sequence[Notice]: ...


class AcademicCalendarRepository(Protocol):
    def list_terms(self) -> Sequence[AcademicTerm]: ...

    def get_term(self, term_id: UUID) -> AcademicTerm | None: ...

    def list_events(self, term_id: UUID) -> Sequence[AcademicEvent]: ...
