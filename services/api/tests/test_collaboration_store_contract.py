"""How the service consumes the ``ports.py`` conflict and read-consistency contract.

The interleavings are injected into the test-only fake (``races``/``conflicts``); this proves the
service's handling of ``StoreConflict`` and its use of locking reads, NOT that a MariaDB adapter
raises/locks that way. Real-DB concurrency tests remain NOT_RUN.
"""

import json

import pytest
from test_collaboration_support import (
    NOW,
    USER_A,
    USER_B,
    FakeStore,
    as_user,
    header_actor,
    mount,
    sequential_ids,
)

from app.features.collaboration import (
    CollaborationDependencies,
    StoreConflict,
    create_collaboration_router,
)
from app.features.collaboration.domain import (
    GroupRole,
    MembershipRecord,
    MembershipStatus,
    ReportReason,
    ReportRecord,
    ReportStatus,
    ReportTargetType,
)
from app.features.collaboration.idempotency import new_record
from app.features.collaboration.ports import like_contains_pattern
from app.features.collaboration.service import MAX_TX_ATTEMPTS

API = "/api/v1"
CONFLICT_MESSAGE = "현재 상태와 충돌합니다."
REPORT_BODY = {"target_type": "anonymous_post", "target_id": "post-1", "reason": "spam"}


@pytest.fixture
def store():
    store = FakeStore()
    store.add_post("post-1", USER_A)
    return store


@pytest.fixture
def client(store):
    deps = CollaborationDependencies(
        actor=header_actor, store=lambda: store, clock=lambda: NOW, id_factory=sequential_ids()
    )
    return mount(create_collaboration_router(deps))


def winner_report(report_id="winner-0001"):
    return ReportRecord(
        id=report_id,
        reporter_id=USER_B,
        target_type=ReportTargetType.ANONYMOUS_POST,
        target_id="post-1",
        reason=ReportReason.SPAM,
        status=ReportStatus.SUBMITTED,
        created_at=NOW,
    )


def commit_winner_report(*, key: str | None):
    """Another request of the same user commits a report (and its claim when ``key`` is set)."""

    def race(store: FakeStore):
        record = winner_report()
        store.commit_elsewhere("reports", record.id, record)
        if key is not None:
            claim = new_record(
                actor_id=USER_B,
                path="/reports",
                key=key,
                payload=REPORT_BODY,
                resource_type="report",
                resource_id=record.id,
            )
            store.commit_elsewhere("claims", claim.scope, claim)

    return race


def assert_plain_conflict(response):
    assert response.status_code == 409
    body = response.json()
    assert body["code"] == "CONFLICT" and body["message"] == CONFLICT_MESSAGE
    text = json.dumps(body, ensure_ascii=False)
    for internal in ("StoreConflict", "1062", "1205", "1213", "Duplicate", "Deadlock", "winner"):
        assert internal not in text


def test_store_conflict_carries_no_text():
    assert StoreConflict().args == () and str(StoreConflict()) == ""
    assert MAX_TX_ATTEMPTS == 2


def test_different_key_concurrent_report_is_409_not_500(client, store):
    # Both requests passed find_report; ours then hits UNIQUE(reporter, target).
    store.races["insert_report"] = commit_winner_report(key="other-tab-key-1")
    response = client.post(
        f"{API}/reports", json=REPORT_BODY, headers=as_user(USER_B, "report-key-0001")
    )
    assert_plain_conflict(response)
    assert response.headers["Cache-Control"] == "private, no-store"
    assert store.transactions == 2  # one retry in a fresh transaction, then the natural 409
    assert list(store.reports) == ["winner-0001"]
    assert [c.scope.key for c in store.claims.values()] == ["other-tab-key-1"]


def test_same_key_race_replays_the_winner_through_a_locking_read(client, store):
    # Our snapshot predates the winner: a plain read would miss it and answer 404.
    store.races["claim"] = commit_winner_report(key="report-key-0001")
    response = client.post(
        f"{API}/reports", json=REPORT_BODY, headers=as_user(USER_B, "report-key-0001")
    )
    assert response.status_code == 201 and response.headers["Idempotent-Replayed"] == "true"
    assert response.json()["data"]["id"] == "winner-0001"
    assert store.transactions == 1 and "get_report" in store.locking_reads


def test_same_key_deadlock_retries_once_then_replays_the_winner(client, store):
    store.races["claim"] = commit_winner_report(key="report-key-0001")
    store.conflicts["claim"] = 1
    response = client.post(
        f"{API}/reports", json=REPORT_BODY, headers=as_user(USER_B, "report-key-0001")
    )
    assert response.status_code == 201 and response.json()["data"]["id"] == "winner-0001"
    assert store.transactions == 2 and list(store.reports) == ["winner-0001"]


def test_persistent_lock_timeout_is_bounded_409_with_full_rollback(client, store):
    store.conflicts["insert_comment"] = 10
    response = client.post(
        f"{API}/anonymous-posts/post-1/comments",
        json={"body": "가상 댓글"},
        headers=as_user(USER_B, "comment-key-0001"),
    )
    assert_plain_conflict(response)
    assert store.transactions == MAX_TX_ATTEMPTS
    assert store.comments == {} and store.claims == {}
    assert store.posts["post-1"].comment_count == 0


def make_group(client, **overrides):
    payload = {"kind": "study", "name": "가상 경합 스터디", "capacity": 3, **overrides}
    created = client.post(f"{API}/groups", json=payload, headers=as_user(USER_A, "group-key-0001"))
    return created.json()["data"]["id"]


def commit_pending_membership(group_id):
    def race(store: FakeStore):
        row = MembershipRecord(
            id="other-tab-membership",
            group_id=group_id,
            user_id=USER_B,
            role=GroupRole.MEMBER,
            status=MembershipStatus.PENDING,
            revision=1,
            created_at=NOW,
            updated_at=NOW,
        )
        store.commit_elsewhere("memberships", row.id, row)

    return race


def test_different_key_concurrent_join_unique_violation_is_409(client, store):
    gid = make_group(client)
    before = store.transactions
    store.races["insert_membership"] = commit_pending_membership(gid)
    response = client.post(
        f"{API}/groups/{gid}/join-requests", headers=as_user(USER_B, "join-key-0001")
    )
    assert_plain_conflict(response)
    assert store.transactions - before == 2
    mine = [m for m in store.memberships.values() if m.user_id == USER_B]
    assert [m.id for m in mine] == ["other-tab-membership"]


def test_membership_is_read_current_under_the_group_lock(client, store):
    gid = make_group(client)
    before = store.transactions
    # The competing request commits while we wait for the group row lock.
    store.races["lock_group"] = commit_pending_membership(gid)
    response = client.post(
        f"{API}/groups/{gid}/join-requests", headers=as_user(USER_B, "join-key-0001")
    )
    assert_plain_conflict(response)
    # Seen by the locking read in the same transaction, not via the UNIQUE fallback.
    assert store.transactions - before == 1 and "memberships_of" in store.locking_reads


def test_decision_and_leave_use_locking_membership_reads(client, store):
    gid = make_group(client, join_mode="approval")
    client.post(f"{API}/groups/{gid}/join-requests", headers=as_user(USER_B, "join-key-0001"))
    pending = client.get(f"{API}/groups/{gid}/join-requests", headers=as_user(USER_A))
    mid = pending.json()["data"]["items"][0]["id"]
    store.locking_reads.clear()
    client.post(
        f"{API}/groups/{gid}/join-requests/{mid}/decision",
        json={"decision": "approve", "revision": 1},
        headers=as_user(USER_A),
    )
    assert store.locking_reads == ["get_membership"]
    store.locking_reads.clear()
    left = client.post(
        f"{API}/groups/{gid}/membership/leave", json={"revision": 2}, headers=as_user(USER_B)
    )
    assert left.status_code == 200 and store.locking_reads == ["memberships_of"]


@pytest.mark.parametrize(
    "text,pattern",
    [
        ("알고리즘", "%알고리즘%"),
        ("100%", "%100\\%%"),
        ("a_b", "%a\\_b%"),
        ("c:\\tmp", "%c:\\\\tmp%"),
        ("\\%_", "%\\\\\\%\\_%"),
    ],
)
def test_like_contains_pattern_escapes_wildcards(text, pattern):
    assert like_contains_pattern(text) == pattern
