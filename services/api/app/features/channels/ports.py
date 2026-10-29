"""Unit-of-work Protocols for free channels. No runtime implementation ships with this feature.

Contract for an approved MariaDB adapter (NOT verified; unit tests use a serialized in-memory
fake only, which proves the service logic, not InnoDB locking):

* ``ChannelsStore.unit_of_work(actor_id)`` opens one transaction bound to the trusted actor.
  Commit only when the context exits normally; any exception rolls back every write in the unit,
  including idempotency claims and member-count updates.
* ``current_memberships()`` reads the actor's CURRENT approved academic memberships from the
  shared ledger inside this transaction (no token/session claim cache), so a department or grade
  change revokes access on the very next request.
* ``is_default_channel(id)`` reads the authoritative campus ``channels`` table. Free-channel
  writes never touch those rows.

Aggregate locks, held until commit/rollback, always taken in this order:

  scope(department_id, grade) -> channel(id)

* ``lock_scope`` serializes create/rename/archive inside one scope so the active-name uniqueness
  and per-owner active count are decided on current rows. ``grade=None`` (department-wide) is its
  own scope key; MariaDB unique indexes accept repeated NULLs, so an adapter should lock a
  dedicated scope row (e.g. ``(department_id, COALESCE(grade, 0))``) rather than rely on a unique
  index. An active-name unique key ``(department_id, grade_key, name_key)`` over ACTIVE rows is
  still recommended as defense in depth.
* ``lock_channel`` is a locking read (``SELECT ... FOR UPDATE``) of the channel row. Join/leave,
  owner edits/archive and official-request submission take it before reading membership,
  member_count, status or the pending request.
* Reads a decision depends on after a lock must be current reads (READ COMMITTED or locking
  reads), because a REPEATABLE READ snapshot may predate the lock. Isolation level not chosen.
* ``update_channel``/``update_request`` are CAS writes: raise ``ApiError(CONFLICT)`` when the stored
  revision differs from ``expected_revision``; store ``row.revision``.
* ``insert_*`` persist the row with its ``IdempotencyClaim`` atomically; claim namespace unique.
* Membership uniqueness is ``(channel_id, user_id)``; at most one PENDING request per channel.
"""

from collections.abc import Sequence
from contextlib import AbstractContextManager
from typing import Protocol
from uuid import UUID

from app.features.academics.idempotency import IdempotencyClaim
from app.features.campus.domain import Membership
from app.features.channels.domain import (
    ChannelMembership,
    FreeChannel,
    OfficialChannelRequest,
)

type Scope = tuple[UUID, int | None]


class ChannelsUnitOfWork(Protocol):
    actor_id: UUID

    def current_memberships(self) -> tuple[Membership, ...]: ...

    def is_default_channel(self, channel_id: UUID) -> bool: ...

    def find_claim(self, namespace: tuple[UUID, str, str, str]) -> IdempotencyClaim | None: ...

    # Locks (see module docstring for order).
    def lock_scope(self, department_id: UUID, grade: int | None) -> None: ...

    def lock_channel(self, channel_id: UUID) -> FreeChannel | None: ...

    # Channels
    def get_channel(self, channel_id: UUID) -> FreeChannel | None: ...

    # ACTIVE channels of the given scopes, seq strictly below ``before_seq``, newest first.
    def list_active(
        self, scopes: Sequence[Scope], before_seq: int | None, limit: int
    ) -> list[FreeChannel]: ...

    def active_name_taken(
        self, department_id: UUID, grade: int | None, name_key: str, exclude_id: UUID | None
    ) -> bool: ...

    def count_owned_active(self, department_id: UUID, grade: int | None) -> int: ...

    def insert_channel(
        self, row: FreeChannel, owner: ChannelMembership, claim: IdempotencyClaim
    ) -> FreeChannel: ...

    def update_channel(self, row: FreeChannel, expected_revision: int) -> None: ...

    # Memberships of the bound actor only
    def my_membership(self, channel_id: UUID) -> ChannelMembership | None: ...

    def my_roles(self, channel_ids: Sequence[UUID]) -> dict[UUID, ChannelMembership]: ...

    # Channels the actor belongs to (any status), channel seq below ``before_seq``, newest first.
    def my_channels(self, before_seq: int | None, limit: int) -> list[FreeChannel]: ...

    def insert_membership(self, row: ChannelMembership) -> None: ...

    def delete_my_membership(self, channel_id: UUID) -> None: ...

    # Official-channel requests
    def pending_request(self, channel_id: UUID) -> OfficialChannelRequest | None: ...

    def get_request(self, request_id: UUID) -> OfficialChannelRequest | None: ...

    def my_requests(self, before_seq: int | None, limit: int) -> list[OfficialChannelRequest]: ...

    def insert_request(
        self, row: OfficialChannelRequest, claim: IdempotencyClaim
    ) -> OfficialChannelRequest: ...

    def update_request(self, row: OfficialChannelRequest, expected_revision: int) -> None: ...


class ChannelsStore(Protocol):
    def unit_of_work(self, actor_id: UUID) -> AbstractContextManager[ChannelsUnitOfWork]: ...
