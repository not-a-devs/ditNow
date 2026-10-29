"""Test-only in-memory unit of work for the collaboration feature.

A global RLock serializes transactions and every table dict is snapshotted on entry and restored
on any exception, so the fake honours the ``ports.py`` contract (all-or-nothing, claim + resource
in one transaction). It is NOT evidence of MariaDB atomicity, isolation, locking or GRANTs and is
never installed in application runtime.
"""

from contextlib import contextmanager
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from threading import RLock

from fastapi import Header
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.factory import create_app
from app.features.collaboration import CollaborationActor, ParticipationGrant
from app.features.collaboration.domain import (
    NO_GROUP_GRANT,
    GroupGrant,
    GroupKind,
    GroupOrigin,
    GroupRecord,
    GroupRole,
    GroupStatus,
    JoinMode,
    MembershipRecord,
    MembershipStatus,
    SourceKind,
    SourceRef,
)
from app.features.community.domain import AnonymousPostPublicRow, PostStatus

NOW = datetime(2026, 10, 30, 3, 0, tzinfo=UTC)
USER_A, USER_B, USER_C = "user-a-0001", "user-b-0002", "user-c-0003"
NAMES = {USER_A: "가상학생A", USER_B: "가상학생B", USER_C: "가상학생C"}

_TABLES = (
    "participation",
    "posts",
    "post_authors",
    "claims",
    "comments",
    "bookmarks",
    "reports",
    "groups",
    "memberships",
    "space_posts",
)


class InjectedFailure(RuntimeError):
    pass


class FakeStore:
    def __init__(self):
        self.lock = RLock()
        self.participation = {USER_A: True, USER_B: True, USER_C: True}
        self.posts: dict[str, AnonymousPostPublicRow] = {}
        self.post_authors: dict[str, str] = {}
        self.claims = {}
        self.comments = {}
        self.bookmarks = {}
        self.reports = {}
        self.groups = {}
        self.memberships = {}
        self.space_posts = {}
        self.names = dict(NAMES)
        self.fail_on: str | None = None
        self.transactions = 0

    @contextmanager
    def transaction(self, actor_id: str):
        with self.lock:
            self.transactions += 1
            snapshot = {name: dict(getattr(self, name)) for name in _TABLES}
            try:
                yield FakeUnitOfWork(self, actor_id)
            except BaseException:
                for name, table in snapshot.items():
                    setattr(self, name, table)
                raise

    # ---------------------------------------------------------------- seeding helpers

    def add_post(self, post_id: str, author: str, *, title="가상 익명 글", body="가상 본문"):
        self.posts[post_id] = AnonymousPostPublicRow(
            id=post_id,
            title=title,
            body=body,
            status=PostStatus.ACTIVE,
            revision=1,
            comment_count=0,
            created_at=NOW - timedelta(hours=len(self.posts) + 1),
            updated_at=NOW,
        )
        self.post_authors[post_id] = author

    def hide_post(self, post_id: str, status=PostStatus.DELETED):
        self.posts[post_id] = replace(self.posts[post_id], status=status)

    def add_catalog_group(self, group_id: str, source: SourceRef, *, leader: str = USER_C):
        self.groups[group_id] = GroupRecord(
            id=group_id,
            kind=GroupKind.CLUB,
            name="카탈로그 동아리",
            description="",
            join_mode=JoinMode.OPEN,
            capacity=10,
            member_count=1,
            status=GroupStatus.OPEN,
            origin=GroupOrigin.CATALOG,
            source=source,
            revision=1,
            created_at=NOW,
            updated_at=NOW,
        )
        membership = MembershipRecord(
            id=f"m-{group_id}",
            group_id=group_id,
            user_id=leader,
            role=GroupRole.LEADER,
            status=MembershipStatus.ACTIVE,
            revision=1,
            created_at=NOW,
            updated_at=NOW,
        )
        self.memberships[membership.id] = membership


class FakeUnitOfWork:
    def __init__(self, store: FakeStore, actor_id: str):
        self.s = store
        self.participation = ParticipationGrant(active=store.participation.get(actor_id, False))

    def _maybe_fail(self, op: str):
        if self.s.fail_on == op:
            self.s.fail_on = None
            raise InjectedFailure(op)

    def claim(self, record):
        stored = self.s.claims.get(record.scope)
        if stored is not None:
            return stored
        self.s.claims[record.scope] = record
        return None

    # posts
    def active_posts(self, post_ids):
        return {
            pid: self.s.posts[pid]
            for pid in post_ids
            if pid in self.s.posts and self.s.posts[pid].status is PostStatus.ACTIVE
        }

    def post_author_is(self, post_id, user_id):
        return self.s.post_authors.get(post_id) == user_id

    def search_posts(self, text, *, limit, offset):
        needle = text.casefold()
        rows = sorted(
            (
                row
                for row in self.s.posts.values()
                if row.status is PostStatus.ACTIVE
                and (needle in row.title.casefold() or needle in row.body.casefold())
            ),
            key=lambda row: row.created_at,
            reverse=True,
        )
        return rows[offset : offset + limit]

    # comments
    def list_comments(self, post_id, *, limit, offset):
        rows = sorted(
            (c for c in self.s.comments.values() if c.post_id == post_id and c.status == "active"),
            key=lambda c: c.created_at,
        )
        return rows[offset : offset + limit]

    def get_comment(self, comment_id):
        return self.s.comments.get(comment_id)

    def insert_comment(self, record):
        self._maybe_fail("insert_comment")
        self.s.comments[record.id] = record
        post = self.s.posts[record.post_id]
        self.s.posts[post.id] = replace(post, comment_count=post.comment_count + 1)

    def cas_comment(self, record, expected_revision):
        current = self.s.comments.get(record.id)
        if current is None or current.revision != expected_revision:
            return False
        self.s.comments[record.id] = record
        if record.status == "deleted" and current.status == "active":
            post = self.s.posts[record.post_id]
            self.s.posts[post.id] = replace(post, comment_count=post.comment_count - 1)
        return True

    # bookmarks
    def add_bookmark(self, record):
        return self.s.bookmarks.setdefault((record.user_id, record.post_id), record)

    def remove_bookmark(self, user_id, post_id):
        return self.s.bookmarks.pop((user_id, post_id), None) is not None

    def list_bookmarks(self, user_id, *, limit, offset):
        rows = sorted(
            (b for (owner, _), b in self.s.bookmarks.items() if owner == user_id),
            key=lambda b: b.created_at,
            reverse=True,
        )
        return rows[offset : offset + limit]

    # reports
    def find_report(self, reporter_id, target_type, target_id):
        return next(
            (
                r
                for r in self.s.reports.values()
                if (r.reporter_id, r.target_type, r.target_id)
                == (reporter_id, target_type, target_id)
            ),
            None,
        )

    def get_report(self, report_id):
        return self.s.reports.get(report_id)

    def insert_report(self, record):
        self._maybe_fail("insert_report")
        self.s.reports[record.id] = record

    def list_reports(self, reporter_id, *, limit, offset):
        rows = [r for r in self.s.reports.values() if r.reporter_id == reporter_id]
        return rows[offset : offset + limit]

    # groups
    def list_groups(self, *, kind, text, limit, offset):
        rows = [
            g
            for g in self.s.groups.values()
            if g.status is GroupStatus.OPEN
            and (kind is None or g.kind is kind)
            and (text is None or text.casefold() in g.name.casefold())
        ]
        return rows[offset : offset + limit]

    def get_group(self, group_id, *, for_update=False):
        return self.s.groups.get(group_id)

    def insert_group(self, record):
        self.s.groups[record.id] = record

    def cas_group(self, record, expected_revision):
        current = self.s.groups.get(record.id)
        if current is None or current.revision != expected_revision:
            return False
        self.s.groups[record.id] = record
        return True

    def group_grant(self, group_id, user_id):
        row = next(
            (
                m
                for m in self.s.memberships.values()
                if m.group_id == group_id and m.user_id == user_id
            ),
            None,
        )
        if row is None or row.status is not MembershipStatus.ACTIVE:
            return NO_GROUP_GRANT
        return GroupGrant(role=row.role, active=True)

    def memberships_of(self, user_id, group_ids):
        wanted = set(group_ids)
        return {
            m.group_id: m
            for m in self.s.memberships.values()
            if m.user_id == user_id and m.group_id in wanted
        }

    def get_membership(self, membership_id):
        return self.s.memberships.get(membership_id)

    def insert_membership(self, record):
        assert not any(
            (m.group_id, m.user_id) == (record.group_id, record.user_id)
            for m in self.s.memberships.values()
        ), "UNIQUE(group_id, user_id)"
        self.s.memberships[record.id] = record

    def cas_membership(self, record, expected_revision):
        current = self.s.memberships.get(record.id)
        if current is None or current.revision != expected_revision:
            return False
        self.s.memberships[record.id] = record
        return True

    def list_memberships(self, group_id, status, *, limit, offset):
        rows = [
            m for m in self.s.memberships.values() if m.group_id == group_id and m.status is status
        ]
        return rows[offset : offset + limit]

    def leader_ids(self, group_ids):
        wanted = set(group_ids)
        return {
            m.group_id: m.user_id
            for m in self.s.memberships.values()
            if m.group_id in wanted and m.role == "leader" and m.status is MembershipStatus.ACTIVE
        }

    def display_names(self, user_ids):
        return {uid: self.s.names[uid] for uid in user_ids if uid in self.s.names}

    # space
    def list_space_posts(self, group_id, *, limit, offset):
        rows = sorted(
            (p for p in self.s.space_posts.values() if p.group_id == group_id),
            key=lambda p: p.created_at,
            reverse=True,
        )
        return [p for p in rows if p.status == "active"][offset : offset + limit]

    def get_space_post(self, post_id):
        return self.s.space_posts.get(post_id)

    def insert_space_post(self, record):
        self.s.space_posts[record.id] = record

    def cas_space_post(self, record, expected_revision):
        current = self.s.space_posts.get(record.id)
        if current is None or current.revision != expected_revision:
            return False
        self.s.space_posts[record.id] = record
        return True


def header_actor(x_test_user: str | None = Header(default=None)) -> CollaborationActor | None:
    """Test-only stand-in for the shared auth dependency (identity only, no roles)."""
    return CollaborationActor(user_id=x_test_user) if x_test_user else None


def sequential_ids(prefix: str = "id"):
    counter = iter(range(1, 1_000_000))
    return lambda: f"{prefix}-{next(counter):04d}"


def mount(feature_router) -> TestClient:
    application = create_app(Settings(environment="test"))
    application.include_router(feature_router, prefix="/api/v1")
    return TestClient(application, raise_server_exceptions=False)


def as_user(user: str, key: str | None = None) -> dict[str, str]:
    headers = {"X-Test-User": user}
    if key is not None:
        headers["Idempotency-Key"] = key
    return headers


OFFICIAL_URL = "https://www.dit.ac.kr/kr/index.php?pCode=example"
SOURCES = {
    "official_ok": SourceRef(SourceKind.OFFICIAL_PUBLIC, OFFICIAL_URL, NOW - timedelta(days=1)),
    "official_no_url": SourceRef(SourceKind.OFFICIAL_PUBLIC, None, NOW - timedelta(days=1)),
    "official_http": SourceRef(
        SourceKind.OFFICIAL_PUBLIC, "http://www.dit.ac.kr/x", NOW - timedelta(days=1)
    ),
    "official_creds": SourceRef(
        SourceKind.OFFICIAL_PUBLIC, "https://u:p@www.dit.ac.kr/x", NOW - timedelta(days=1)
    ),
    "official_future": SourceRef(SourceKind.OFFICIAL_PUBLIC, OFFICIAL_URL, NOW + timedelta(days=1)),
    "official_naive": SourceRef(SourceKind.OFFICIAL_PUBLIC, OFFICIAL_URL, datetime(2026, 10, 1)),
    "demo_with_url": SourceRef(SourceKind.DEMO, OFFICIAL_URL, NOW),
    "unknown": SourceRef(SourceKind.UNKNOWN),
}
