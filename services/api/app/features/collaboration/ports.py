"""Persistence contracts for the collaboration feature (no production adapter in this package).

The shared DB owner implements ``CollaborationStore`` on MariaDB (InnoDB). Until then the router
answers 503. The in-memory fake under ``tests/`` only exercises these contracts; it proves
nothing about real DB atomicity, isolation or GRANTs.

Unit-of-work contract (one DB transaction per ``transaction()`` block):

- Commit on clean exit, roll back everything on any exception (no partial writes).
- ``participation`` and ``group_grant`` are read from server-side ledgers INSIDE the transaction
  (not from the token), so a revoked grant blocks the request, including idempotent replays.
- ``claim`` inserts into a table with UNIQUE(actor_id, method, canonical_path, key) and returns
  ``None``. If the scope exists it writes nothing and returns the stored record; a concurrent
  duplicate must block on the unique key and then observe the winner's record. The claim and the
  resource row commit or roll back together. Records are never removed (tombstones survive
  resource deletion).
- ``cas_*`` update only when the stored revision equals ``expected_revision`` and return
  ``False`` otherwise.
- ``get_group(..., for_update=True)`` takes a row lock (``SELECT ... FOR UPDATE``) so capacity
  checks and ``member_count`` changes serialize per group.
- Anonymous post reads use ONLY the community public projection (``anonymous_posts_public``);
  they never join ``anonymous_posts_private`` into a response. ``post_author_is`` is the one
  server-internal ownership probe (self-report check) and its result never leaves the service.
- ``insert_comment``/``cas_comment`` must keep ``anonymous_posts_public.comment_count`` in sync
  in the same transaction (community projection owner + DB owner).
"""

from collections.abc import Iterable, Sequence
from contextlib import AbstractContextManager
from typing import Protocol

from app.features.collaboration.domain import (
    BookmarkRecord,
    CommentRecord,
    GroupGrant,
    GroupKind,
    GroupRecord,
    MembershipRecord,
    MembershipStatus,
    ParticipationGrant,
    ReportRecord,
    ReportTargetType,
    SpacePostRecord,
)
from app.features.collaboration.idempotency import IdempotencyRecord
from app.features.community.domain import AnonymousPostPublicRow


class CollaborationUnitOfWork(Protocol):
    participation: ParticipationGrant

    # -------------------------------------------------------------- idempotency (all creates)
    def claim(self, record: IdempotencyRecord) -> IdempotencyRecord | None: ...

    # -------------------------------------------------------------- anonymous post seam
    def active_posts(self, post_ids: Iterable[str]) -> dict[str, AnonymousPostPublicRow]:
        """Active posts from the public projection only, keyed by ID (batch, no N+1)."""
        ...

    def post_author_is(self, post_id: str, user_id: str) -> bool: ...

    def search_posts(self, text: str, *, limit: int, offset: int) -> list[AnonymousPostPublicRow]:
        """Active posts whose public title/body contains ``text``; newest first."""
        ...

    # -------------------------------------------------------------- comments (FR-COM-002)
    def list_comments(self, post_id: str, *, limit: int, offset: int) -> list[CommentRecord]:
        """Active comments of one post, oldest first."""
        ...

    def get_comment(self, comment_id: str) -> CommentRecord | None: ...

    def insert_comment(self, record: CommentRecord) -> None: ...

    def cas_comment(self, record: CommentRecord, expected_revision: int) -> bool: ...

    # -------------------------------------------------------------- bookmarks (FR-COM-002)
    def add_bookmark(self, record: BookmarkRecord) -> BookmarkRecord:
        """Insert-if-absent on UNIQUE(user_id, post_id); returns the stored row."""
        ...

    def remove_bookmark(self, user_id: str, post_id: str) -> bool: ...

    def list_bookmarks(self, user_id: str, *, limit: int, offset: int) -> list[BookmarkRecord]: ...

    # -------------------------------------------------------------- reports (FR-COM-003)
    def find_report(
        self, reporter_id: str, target_type: ReportTargetType, target_id: str
    ) -> ReportRecord | None: ...

    def get_report(self, report_id: str) -> ReportRecord | None: ...

    def insert_report(self, record: ReportRecord) -> None:
        """UNIQUE(reporter_id, target_type, target_id)."""
        ...

    def list_reports(self, reporter_id: str, *, limit: int, offset: int) -> list[ReportRecord]: ...

    # -------------------------------------------------------------- groups (FR-COM-006)
    def list_groups(
        self, *, kind: GroupKind | None, text: str | None, limit: int, offset: int
    ) -> list[GroupRecord]:
        """Discoverable (open) groups only."""
        ...

    def get_group(self, group_id: str, *, for_update: bool = False) -> GroupRecord | None: ...

    def insert_group(self, record: GroupRecord) -> None: ...

    def cas_group(self, record: GroupRecord, expected_revision: int) -> bool: ...

    def group_grant(self, group_id: str, user_id: str) -> GroupGrant: ...

    def memberships_of(
        self, user_id: str, group_ids: Iterable[str]
    ) -> dict[str, MembershipRecord]: ...

    def get_membership(self, membership_id: str) -> MembershipRecord | None: ...

    def insert_membership(self, record: MembershipRecord) -> None:
        """UNIQUE(group_id, user_id)."""
        ...

    def cas_membership(self, record: MembershipRecord, expected_revision: int) -> bool: ...

    def list_memberships(
        self, group_id: str, status: MembershipStatus, *, limit: int, offset: int
    ) -> list[MembershipRecord]: ...

    def leader_ids(self, group_ids: Iterable[str]) -> dict[str, str]: ...

    def display_names(self, user_ids: Iterable[str]) -> dict[str, str]:
        """Allowed public activity display names only (no email/student number/department)."""
        ...

    # -------------------------------------------------------------- team space (FR-COM-007)
    def list_space_posts(
        self, group_id: str, *, limit: int, offset: int
    ) -> Sequence[SpacePostRecord]:
        """Active posts of one group, newest first."""
        ...

    def get_space_post(self, post_id: str) -> SpacePostRecord | None: ...

    def insert_space_post(self, record: SpacePostRecord) -> None: ...

    def cas_space_post(self, record: SpacePostRecord, expected_revision: int) -> bool: ...


class CollaborationStore(Protocol):
    def transaction(self, actor_id: str) -> AbstractContextManager[CollaborationUnitOfWork]: ...
