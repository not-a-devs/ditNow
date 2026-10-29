"""Persistence contracts for the collaboration feature (no production adapter in this package).

The shared DB owner implements ``CollaborationStore`` on MariaDB (InnoDB). Until then the router
answers 503. The in-memory fake under ``tests/`` only exercises these contracts; it proves
nothing about real DB atomicity, isolation, locking or GRANTs. Whether the deployed server runs
REPEATABLE READ or READ COMMITTED is NOT confirmed here; the adapter must satisfy the read rules
below under whichever level it uses.

Unit-of-work contract (one DB transaction per ``transaction()`` block):

- Commit on clean exit, roll back everything on any exception (no partial writes).
- Errors: a UNIQUE violation (MariaDB 1062), lock wait timeout (1205) or deadlock (1213) raised
  anywhere in the block is translated by the adapter into ``StoreConflict()`` after the rollback.
  ``StoreConflict`` carries no driver/SQL text (raise it ``from None``); any other driver error
  stays an internal error. The service consumes ``StoreConflict`` by re-running the whole request
  in ONE new transaction (``MAX_TX_ATTEMPTS`` = 2, no backoff): a same-key race then replays the
  winner's committed record, a different-key natural duplicate (report target, membership) then
  meets the existing row and answers 409, and a second ``StoreConflict`` answers 409.

Read consistency. Under MariaDB REPEATABLE READ a plain SELECT reads the snapshot fixed by the
transaction's first consistent read, so rows another transaction committed meanwhile stay
invisible; locking reads (``FOR UPDATE`` / ``LOCK IN SHARE MODE``) read the latest committed
version and lock it. Sources (checked 2026-10-30):
https://mariadb.com/docs/server/reference/sql-statements/transactions/transactions-repeatable-read
https://mariadb.com/docs/server/reference/sql-statements/data-manipulation/selecting-data/for-update
The adapter must therefore use EITHER an approved per-transaction READ COMMITTED level OR
locking reads for these current reads:

- ``participation``, ``participation_of`` and ``group_grant``: current ledger reads
  (``LOCK IN SHARE MODE``), so a concurrent revocation waits for this transaction and is never
  hidden by a stale snapshot. The token/actor never carries these grants.
- ``claim``: INSERT on UNIQUE(actor_id, method, canonical_path, key) returning ``None``. On a
  duplicate it writes nothing and returns the stored record through a locking read; a concurrent
  duplicate blocks on the unique key and then observes the winner's committed record (or gets
  1062/1205/1213 -> ``StoreConflict`` -> retry). Claim and resource commit or roll back together.
  Records are never removed (tombstones survive resource deletion).
- Every getter called with ``for_update=True`` is ``SELECT ... FOR UPDATE`` (latest committed
  version, row lock until commit). The service passes it for: the winner row read after a claim
  replay, the target row of an update/delete, ``find_report`` before ``insert_report``, and every
  membership read made under the group lock (join, decision, leave).
- ``get_group(..., for_update=True)`` locks the group row so capacity checks, ``member_count``
  changes and membership transitions serialize per group.

Lock order inside one transaction (keep it to avoid deadlocks; a deadlock that still happens is
``StoreConflict``): actor participation (S) -> parent row (group ``FOR UPDATE`` / post projection)
-> idempotency claim -> child rows ``FOR UPDATE`` (comment, report, membership, space post) ->
other user's participation (``participation_of``) -> writes. Counters (``member_count``,
``comment_count``) are updated on rows already locked in this order.

Uniqueness owned by the DB: claims UNIQUE(actor_id, method, canonical_path, key); reports
UNIQUE(reporter_id, target_type, target_id); memberships UNIQUE(group_id, user_id); bookmarks
UNIQUE(user_id, post_id) (``add_bookmark`` is insert-if-absent, e.g. ``INSERT IGNORE`` + locking
read).

Other obligations:

- ``cas_*`` update only when the stored revision equals ``expected_revision`` and return
  ``False`` otherwise.
- Anonymous post reads use ONLY the community public projection (``anonymous_posts_public``);
  they never join ``anonymous_posts_private`` into a response. ``post_author_is`` is the one
  server-internal ownership probe (self-report check) and its result never leaves the service.
- ``insert_comment``/``cas_comment`` must keep ``anonymous_posts_public.comment_count`` in sync
  in the same transaction (community projection owner + DB owner), also when the comment's post
  is no longer active (owner tombstone delete).
- Text search (``search_posts``, ``list_groups(text=...)``) is a parameterized
  ``LIKE ? ESCAPE '\\'`` whose pattern comes from ``like_contains_pattern``, so ``%``, ``_`` and
  ``\\`` in user text match literally; the text is never concatenated into SQL. Case/accent
  folding follows the column collation (not decided here). Results use a total order with an ID
  tie-breaker (``created_at DESC, id DESC``) so offset pages neither repeat nor skip rows sharing
  a timestamp; pages can still shift when rows are inserted between page requests.
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

LIKE_ESCAPE = "\\"


class StoreConflict(Exception):  # noqa: N818 - domain signal from the adapter, not a driver error
    """UNIQUE violation, lock wait timeout or deadlock, already rolled back. Carries no text."""

    def __init__(self) -> None:
        super().__init__()


def like_contains_pattern(text: str) -> str:
    """``LIKE`` pattern that matches ``text`` literally as a substring (with ``ESCAPE '\\'``)."""
    escaped = (
        text.replace(LIKE_ESCAPE, LIKE_ESCAPE * 2)
        .replace("%", LIKE_ESCAPE + "%")
        .replace("_", LIKE_ESCAPE + "_")
    )
    return f"%{escaped}%"


class CollaborationUnitOfWork(Protocol):
    participation: ParticipationGrant

    def participation_of(self, user_id: str) -> ParticipationGrant:
        """Another user's current participation (e.g. a join applicant); same ledger rules."""
        ...

    # -------------------------------------------------------------- idempotency (all creates)
    def claim(self, record: IdempotencyRecord) -> IdempotencyRecord | None: ...

    # -------------------------------------------------------------- anonymous post seam
    def active_posts(self, post_ids: Iterable[str]) -> dict[str, AnonymousPostPublicRow]:
        """Active posts from the public projection only, keyed by ID (batch, no N+1)."""
        ...

    def post_author_is(self, post_id: str, user_id: str) -> bool: ...

    def search_posts(self, text: str, *, limit: int, offset: int) -> list[AnonymousPostPublicRow]:
        """Active posts whose public title/body contains ``text`` literally (escaped LIKE);
        ``created_at DESC, id DESC``."""
        ...

    # -------------------------------------------------------------- comments (FR-COM-002)
    def list_comments(self, post_id: str, *, limit: int, offset: int) -> list[CommentRecord]:
        """Active comments of one post, oldest first."""
        ...

    def get_comment(self, comment_id: str, *, for_update: bool = False) -> CommentRecord | None: ...

    def insert_comment(self, record: CommentRecord) -> None: ...

    def cas_comment(self, record: CommentRecord, expected_revision: int) -> bool: ...

    # -------------------------------------------------------------- bookmarks (FR-COM-002)
    def add_bookmark(self, record: BookmarkRecord) -> BookmarkRecord:
        """Insert-if-absent on UNIQUE(user_id, post_id); returns the stored row."""
        ...

    def remove_bookmark(self, user_id: str, post_id: str) -> bool: ...

    def list_bookmarks(self, user_id: str, *, limit: int, offset: int) -> list[BookmarkRecord]: ...

    def bookmarked_among(self, user_id: str, post_ids: Iterable[str]) -> set[str]:
        """Subset of ``post_ids`` the user has bookmarked (batch, caller's own rows only)."""
        ...

    # -------------------------------------------------------------- reports (FR-COM-003)
    def find_report(
        self,
        reporter_id: str,
        target_type: ReportTargetType,
        target_id: str,
        *,
        for_update: bool = False,
    ) -> ReportRecord | None: ...

    def get_report(self, report_id: str, *, for_update: bool = False) -> ReportRecord | None: ...

    def insert_report(self, record: ReportRecord) -> None:
        """UNIQUE(reporter_id, target_type, target_id); a violation is ``StoreConflict``."""
        ...

    def list_reports(self, reporter_id: str, *, limit: int, offset: int) -> list[ReportRecord]: ...

    # -------------------------------------------------------------- groups (FR-COM-006)
    def list_groups(
        self, *, kind: GroupKind | None, text: str | None, limit: int, offset: int
    ) -> list[GroupRecord]:
        """Discoverable (open) groups only; ``text`` is an escaped LIKE on the name."""
        ...

    def get_group(self, group_id: str, *, for_update: bool = False) -> GroupRecord | None: ...

    def insert_group(self, record: GroupRecord) -> None: ...

    def cas_group(self, record: GroupRecord, expected_revision: int) -> bool: ...

    def group_grant(self, group_id: str, user_id: str) -> GroupGrant: ...

    def memberships_of(
        self, user_id: str, group_ids: Iterable[str], *, for_update: bool = False
    ) -> dict[str, MembershipRecord]: ...

    def get_membership(
        self, membership_id: str, *, for_update: bool = False
    ) -> MembershipRecord | None: ...

    def insert_membership(self, record: MembershipRecord) -> None:
        """UNIQUE(group_id, user_id); a violation is ``StoreConflict``."""
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

    def get_space_post(
        self, post_id: str, *, for_update: bool = False
    ) -> SpacePostRecord | None: ...

    def insert_space_post(self, record: SpacePostRecord) -> None: ...

    def cas_space_post(self, record: SpacePostRecord, expected_revision: int) -> bool: ...


class CollaborationStore(Protocol):
    def transaction(self, actor_id: str) -> AbstractContextManager[CollaborationUnitOfWork]: ...
