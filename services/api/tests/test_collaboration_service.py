"""Service/domain tests: idempotency scope, concurrency on the fake UOW, provenance rules."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime, timedelta, timezone

import pytest
from test_collaboration_support import NOW, USER_A, FakeStore, FakeUnitOfWork, sequential_ids

from app.core.errors import ApiError
from app.features.collaboration import CollaborationActor, CollaborationService
from app.features.collaboration.domain import (
    SourceKind,
    SourceRef,
    excerpt,
    is_safe_public_url,
    normalize_source,
)
from app.features.collaboration.idempotency import (
    IdempotencyScope,
    new_record,
    payload_hash,
    replayed_resource,
)
from app.features.collaboration.schemas import CommentCreate, GroupCreate
from app.schemas.common import ErrorCode


def service(store, ids=None):
    return CollaborationService(store, clock=lambda: NOW, id_factory=ids or sequential_ids())


def record(**overrides):
    base = dict(
        actor_id="a",
        path="/reports",
        key="key-00000001",
        payload={"x": 1},
        resource_type="report",
        resource_id="r1",
    )
    return new_record(**{**base, **overrides})


def test_scope_is_actor_method_canonical_path_and_key():
    rec = record()
    assert rec.scope == IdempotencyScope("a", "POST", "/api/v1/reports", "key-00000001")
    assert rec.payload_hash == payload_hash({"x": 1})
    assert payload_hash({"a": 1, "b": 2}) == payload_hash({"b": 2, "a": 1})


def test_replay_rules():
    attempted = record(resource_id="new")
    assert replayed_resource(None, attempted) is None
    assert replayed_resource(record(resource_id="old"), attempted) == "old"
    with pytest.raises(ApiError) as conflict:
        replayed_resource(record(payload={"x": 2}), attempted)
    assert conflict.value.code is ErrorCode.CONFLICT
    for foreign in (record(actor_id="b"), record(path="/groups"), record(resource_type="group")):
        with pytest.raises(ApiError) as leak:
            replayed_resource(foreign, attempted)
        assert leak.value.code is ErrorCode.INTERNAL


def test_adapter_returning_foreign_claim_fails_closed(monkeypatch):
    store = FakeStore()
    store.add_post("p1", "someone")
    svc = service(store)
    foreign = record(actor_id="user-b-0002", path="/anonymous-posts/p1/comments")
    foreign = replace(foreign, payload_hash=payload_hash({"body": "x"}), resource_type="comment")
    monkeypatch.setattr(FakeUnitOfWork, "claim", lambda self, rec: foreign)
    with pytest.raises(ApiError) as error:
        svc.create_comment(
            CollaborationActor(USER_A), "p1", CommentCreate(body="x"), "key-00000001"
        )
    assert error.value.code is ErrorCode.INTERNAL
    assert store.comments == {}


def test_concurrent_joins_never_exceed_capacity():
    store = FakeStore()
    users = [f"user-{n:04d}" for n in range(12)]
    store.participation.update({user: True for user in users})
    svc = service(store)
    group, _ = svc.create_group(
        CollaborationActor(USER_A),
        GroupCreate(kind="study", name="동시성 스터디", capacity=4, join_mode="open"),
        "group-key-0001",
    )

    def join(user):
        try:
            svc.request_join(CollaborationActor(user), group.id, f"join-{user}")
            return "ok"
        except ApiError as error:
            return error.code

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(join, users))
    assert results.count("ok") == 3
    assert results.count(ErrorCode.CONFLICT) == len(users) - 3
    assert store.groups[group.id].member_count == 4
    active = [m for m in store.memberships.values() if m.status == "active"]
    assert len(active) == 4


def test_concurrent_same_key_creates_one_comment():
    store = FakeStore()
    store.add_post("p1", "someone")
    svc = service(store)
    actor = CollaborationActor(USER_A)

    def send(_):
        comment, replayed = svc.create_comment(
            actor, "p1", CommentCreate(body="동시"), "same-key-0001"
        )
        return comment.id, replayed

    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(send, range(6)))
    assert len({cid for cid, _ in results}) == 1
    assert [replayed for _, replayed in results].count(False) == 1
    assert len(store.comments) == 1


def test_failed_write_rolls_back_claim_and_counter():
    store = FakeStore()
    store.add_post("p1", "someone")
    svc = service(store)
    actor = CollaborationActor(USER_A)
    store.fail_on = "insert_comment"
    with pytest.raises(RuntimeError):
        svc.create_comment(actor, "p1", CommentCreate(body="x"), "key-00000001")
    assert store.claims == {} and store.comments == {}
    assert store.posts["p1"].comment_count == 0
    comment, replayed = svc.create_comment(actor, "p1", CommentCreate(body="x"), "key-00000001")
    assert replayed is False and len(store.comments) == 1


@pytest.mark.parametrize(
    "url,ok",
    [
        ("https://www.dit.ac.kr/kr/index.php?pCode=a", True),
        ("http://www.dit.ac.kr/", False),
        ("javascript:alert(1)", False),
        ("https://user@www.dit.ac.kr/", False),
        ("https://www.dit.ac.kr/#frag", False),
        ("https://www.dit.ac.kr/ x", False),
        ("https://www.dit.ac.kr:99999/", False),
        ("https:///nohost", False),
        ("https://" + "a" * 2050 + ".kr", False),
        (None, False),
    ],
)
def test_safe_public_url(url, ok):
    assert is_safe_public_url(url) is ok


def test_normalize_source_keeps_demo_unknown_distinct_and_utc():
    kst = datetime(2026, 10, 29, 18, 0, tzinfo=timezone(timedelta(hours=9)))
    official = normalize_source(
        SourceRef(SourceKind.OFFICIAL_PUBLIC, "https://www.dit.ac.kr/", kst), NOW
    )
    assert official.kind is SourceKind.OFFICIAL_PUBLIC
    assert official.checked_at == datetime(2026, 10, 29, 9, 0, tzinfo=UTC)
    assert official.checked_at.tzinfo is UTC
    assert normalize_source(SourceRef(SourceKind.DEMO, "https://x.kr/", NOW), NOW) == SourceRef(
        SourceKind.DEMO
    )
    assert normalize_source(SourceRef(SourceKind.UNKNOWN), NOW).kind is SourceKind.UNKNOWN
    assert normalize_source(SourceRef(SourceKind.USER_DEMO), NOW).kind is SourceKind.USER_DEMO


def test_excerpt_is_bounded_and_whitespace_collapsed():
    assert excerpt("a\n\n b") == "a b"
    assert len(excerpt("가" * 500)) == 120
