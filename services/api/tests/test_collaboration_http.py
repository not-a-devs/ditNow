"""HTTP contract tests for the collaboration router (TC-V1-COM-002/003/006/007, TC-V1-X02).

Uses the test-only fake unit of work; no DB, auth provider or network is involved.
"""

import json

import pytest
from test_collaboration_support import (
    NAMES,
    NOW,
    SOURCES,
    USER_A,
    USER_B,
    USER_C,
    FakeStore,
    as_user,
    header_actor,
    mount,
    sequential_ids,
)

from app.features.collaboration import (
    CollaborationDependencies,
    create_collaboration_router,
    router,
)
from app.features.community.domain import PostStatus

ERROR_KEYS = {"code", "message", "field_errors", "retryable", "request_id"}
API = "/api/v1"


@pytest.fixture
def store():
    store = FakeStore()
    store.add_post("post-1", USER_A, title="알고리즘 스터디 후기", body="가상 본문 내용")
    store.add_post("post-2", USER_B, title="학식 메뉴", body="오늘 메뉴 이야기")
    return store


@pytest.fixture
def client(store):
    deps = CollaborationDependencies(
        actor=header_actor,
        store=lambda: store,
        clock=lambda: NOW,
        id_factory=sequential_ids(),
    )
    return mount(create_collaboration_router(deps))


def comment(client, user=USER_B, body="가상 댓글", key="comment-key-0001", post="post-1"):
    return client.post(
        f"{API}/anonymous-posts/{post}/comments", json={"body": body}, headers=as_user(user, key)
    )


def make_group(client, user=USER_A, key="group-key-0001", **overrides):
    payload = {"kind": "study", "name": "가상 알고리즘 스터디", "capacity": 3, **overrides}
    return client.post(f"{API}/groups", json=payload, headers=as_user(user, key))


def leaks_identity(body: object) -> bool:
    text = json.dumps(body, ensure_ascii=False)
    return any(uid in text for uid in (USER_A, USER_B, USER_C)) or any(
        name in text for name in NAMES.values()
    )


# ---------------------------------------------------------------- fail closed / ordering


@pytest.mark.parametrize(
    "method,path",
    [
        ("get", "/search/anonymous-posts?q=ab"),
        ("get", "/anonymous-posts/p1/comments"),
        ("get", "/me/bookmarks"),
        ("get", "/me/reports"),
        ("get", "/groups"),
        ("get", "/groups/g1/space/posts"),
    ],
)
def test_default_router_fails_closed_with_private_503(method, path):
    response = getattr(mount(router), method)(API + path)
    assert response.status_code == 503
    assert set(response.json()) == ERROR_KEYS
    assert response.headers["Cache-Control"] == "private, no-store"


def test_auth_is_resolved_before_store():
    touched = []

    def store():
        touched.append(True)
        return FakeStore()

    unconfigured = mount(create_collaboration_router(CollaborationDependencies(store=store)))
    assert unconfigured.get(f"{API}/groups").status_code == 503
    anonymous = mount(
        create_collaboration_router(CollaborationDependencies(actor=header_actor, store=store))
    )
    assert anonymous.get(f"{API}/groups").status_code == 401
    assert touched == []


def test_revoked_participation_is_403_everywhere(client, store):
    store.participation[USER_B] = False
    for path in ("/me/bookmarks", "/groups", "/anonymous-posts/post-1/comments"):
        response = client.get(API + path, headers=as_user(USER_B))
        assert response.status_code == 403
        assert response.headers["Cache-Control"] == "private, no-store"


def test_no_operator_review_sanction_block_or_appeal_routes():
    paths = {route.path for route in router.routes}
    assert not any(
        word in path for path in paths for word in ("admin", "sanction", "block", "appeal")
    )
    assert "/reports" in paths and "/reports/{report_id}" not in paths


# ---------------------------------------------------------------- FR-COM-002 comments


def test_comment_is_anonymous_and_is_mine_is_per_caller(client):
    created = comment(client)
    assert created.status_code == 201
    data = created.json()["data"]
    assert set(data) == {
        "id",
        "post_id",
        "display_name",
        "body",
        "is_mine",
        "revision",
        "created_at",
        "updated_at",
    }
    assert data["display_name"] == "익명" and data["is_mine"] is True
    assert not leaks_identity(created.json())
    seen_by_a = client.get(f"{API}/anonymous-posts/post-1/comments", headers=as_user(USER_A))
    assert seen_by_a.json()["data"]["items"][0]["is_mine"] is False
    assert seen_by_a.headers["Cache-Control"] == "private, no-store"
    assert not leaks_identity(seen_by_a.json())


def test_comment_rejects_injected_author_and_keeps_markup_as_text(client):
    injected = client.post(
        f"{API}/anonymous-posts/post-1/comments",
        json={"body": "x", "author_id": USER_A},
        headers=as_user(USER_B, "comment-key-0001"),
    )
    assert injected.status_code == 400
    script = comment(client, body="<script>alert(1)</script>")
    assert script.json()["data"]["body"] == "<script>alert(1)</script>"


@pytest.mark.parametrize("body", ["", "   ", "a\x00b", "x" * 1001])
def test_comment_body_validation(client, body):
    assert comment(client, body=body).status_code == 400


def test_comment_idempotency_replay_conflict_and_scope(client, store):
    first = comment(client)
    again = comment(client)
    assert again.status_code == 201 and again.headers["Idempotent-Replayed"] == "true"
    assert again.json()["data"]["id"] == first.json()["data"]["id"]
    assert len(store.comments) == 1 and store.posts["post-1"].comment_count == 1
    assert comment(client, body="다른 내용").status_code == 409
    # Same key under another parent path or another actor is a different request.
    assert comment(client, post="post-2").json()["data"]["id"] != first.json()["data"]["id"]
    assert comment(client, user=USER_C).json()["data"]["id"] != first.json()["data"]["id"]
    assert len(store.comments) == 3


@pytest.mark.parametrize("key", [None, "short", "has a space 01", "k" * 129])
def test_comment_key_required_and_validated(client, store, key):
    headers = as_user(USER_B) if key is None else as_user(USER_B, key)
    response = client.post(
        f"{API}/anonymous-posts/post-1/comments", json={"body": "x"}, headers=headers
    )
    assert response.status_code == 400 and store.comments == {}


def test_replay_after_delete_is_404_tombstone_not_resurrected(client, store):
    created = comment(client).json()["data"]
    deleted = client.delete(
        f"{API}/anonymous-posts/post-1/comments/{created['id']}?revision=1",
        headers=as_user(USER_B),
    )
    assert deleted.status_code == 200 and deleted.json()["data"] == {
        "id": created["id"],
        "deleted": True,
    }
    tombstone = store.comments[created["id"]]
    assert tombstone.status == "deleted" and tombstone.body == ""
    assert comment(client).status_code == 404
    assert len(store.comments) == 1 and len(store.claims) == 1
    listed = client.get(f"{API}/anonymous-posts/post-1/comments", headers=as_user(USER_B))
    assert listed.json()["data"]["items"] == []


def test_replay_after_permission_revoked_is_refused(client, store):
    comment(client)
    store.participation[USER_B] = False
    assert comment(client).status_code == 403


def test_comment_update_owner_revision_and_parent_scope(client, store):
    cid = comment(client).json()["data"]["id"]
    url = f"{API}/anonymous-posts/post-1/comments/{cid}"
    assert (
        client.patch(url, json={"revision": 1, "body": "수정"}, headers=as_user(USER_A)).status_code
        == 404
    )
    wrong_parent = f"{API}/anonymous-posts/post-2/comments/{cid}"
    assert (
        client.patch(
            wrong_parent, json={"revision": 1, "body": "수정"}, headers=as_user(USER_B)
        ).status_code
        == 404
    )
    ok = client.patch(url, json={"revision": 1, "body": "수정"}, headers=as_user(USER_B))
    assert ok.status_code == 200 and ok.json()["resource_version"] == 2
    stale = client.patch(url, json={"revision": 1, "body": "또"}, headers=as_user(USER_B))
    assert stale.status_code == 409
    assert client.delete(f"{url}?revision=1", headers=as_user(USER_B)).status_code == 409
    assert client.delete(f"{url}?revision=2", headers=as_user(USER_A)).status_code == 404


def test_comments_on_hidden_or_missing_post_are_404(client, store):
    store.hide_post("post-2")
    for post in ("post-2", "missing"):
        assert (
            client.get(
                f"{API}/anonymous-posts/{post}/comments", headers=as_user(USER_A)
            ).status_code
            == 404
        )
        assert comment(client, post=post).status_code == 404


@pytest.mark.parametrize("status", ["hidden", "deleted"])
def test_author_can_tombstone_own_comment_after_post_is_hidden(client, store, status):
    cid = comment(client, user=USER_A, post="post-2", body="지우고 싶은 가상 댓글").json()["data"][
        "id"
    ]
    other = comment(client, user=USER_C, post="post-2", key="comment-key-0002").json()["data"]["id"]
    store.hide_post("post-2", PostStatus(status))
    url = f"{API}/anonymous-posts/post-2/comments/{cid}"
    # Create/update/list keep requiring an active parent.
    assert (
        client.get(f"{API}/anonymous-posts/post-2/comments", headers=as_user(USER_A)).status_code
        == 404
    )
    assert (
        client.patch(url, json={"revision": 1, "body": "수정"}, headers=as_user(USER_A)).status_code
        == 404
    )
    assert comment(client, user=USER_A, post="post-2", key="comment-key-0003").status_code == 404
    # Delete still checks author, parent ID, status and revision.
    assert client.delete(f"{url}?revision=1", headers=as_user(USER_B)).status_code == 404
    wrong_parent = f"{API}/anonymous-posts/post-1/comments/{cid}?revision=1"
    assert client.delete(wrong_parent, headers=as_user(USER_A)).status_code == 404
    assert client.delete(f"{url}?revision=9", headers=as_user(USER_A)).status_code == 409
    store.participation[USER_A] = False
    assert client.delete(f"{url}?revision=1", headers=as_user(USER_A)).status_code == 403
    store.participation[USER_A] = True
    deleted = client.delete(f"{url}?revision=1", headers=as_user(USER_A))
    assert deleted.status_code == 200 and deleted.json()["data"] == {"id": cid, "deleted": True}
    assert store.comments[cid].body == "" and store.comments[cid].status == "deleted"
    assert client.delete(f"{url}?revision=2", headers=as_user(USER_A)).status_code == 404
    # Other comments under the hidden post are untouched.
    assert store.comments[other].status == "active"


# ---------------------------------------------------------------- FR-COM-002 bookmarks/search


def test_bookmarks_are_private_and_hide_deleted_posts(client, store):
    assert client.put(f"{API}/me/bookmarks/post-1", headers=as_user(USER_B)).json()["data"] == {
        "post_id": "post-1",
        "bookmarked": True,
    }
    assert client.put(f"{API}/me/bookmarks/post-1", headers=as_user(USER_B)).status_code == 200
    client.put(f"{API}/me/bookmarks/post-2", headers=as_user(USER_B))
    assert len(store.bookmarks) == 2
    mine = client.get(f"{API}/me/bookmarks", headers=as_user(USER_B)).json()["data"]["items"]
    assert {item["post"]["id"] for item in mine} == {"post-1", "post-2"}
    assert not leaks_identity(mine)
    assert client.get(f"{API}/me/bookmarks", headers=as_user(USER_A)).json()["data"]["items"] == []
    store.hide_post("post-2")
    mine = client.get(f"{API}/me/bookmarks", headers=as_user(USER_B)).json()["data"]["items"]
    assert [item["post"]["id"] for item in mine] == ["post-1"]
    assert client.put(f"{API}/me/bookmarks/post-2", headers=as_user(USER_B)).status_code == 404
    removed = client.delete(f"{API}/me/bookmarks/post-2", headers=as_user(USER_B))
    assert removed.json()["data"]["bookmarked"] is False and len(store.bookmarks) == 1


def test_search_uses_public_projection_only(client, store):
    store.add_post("post-3", USER_C, title="스터디 모집 아님", body="숨김")
    store.hide_post("post-3")
    found = client.get(f"{API}/search/anonymous-posts?q=스터디", headers=as_user(USER_B))
    assert found.status_code == 200
    items = found.json()["data"]["items"]
    assert [item["id"] for item in items] == ["post-1"]
    assert set(items[0]) == {
        "id",
        "display_name",
        "title",
        "excerpt",
        "comment_count",
        "bookmarked",
        "created_at",
    }
    assert items[0]["bookmarked"] is False
    assert not leaks_identity(found.json())


def test_search_and_bookmark_list_report_the_callers_own_bookmark_state(client, store):
    client.put(f"{API}/me/bookmarks/post-1", headers=as_user(USER_B))
    search = f"{API}/search/anonymous-posts?q=스터디"
    mine = client.get(search, headers=as_user(USER_B)).json()["data"]["items"]
    assert [(item["id"], item["bookmarked"]) for item in mine] == [("post-1", True)]
    # Another user's bookmark never shows up as someone else's state.
    other = client.get(search, headers=as_user(USER_C)).json()["data"]["items"]
    assert [(item["id"], item["bookmarked"]) for item in other] == [("post-1", False)]
    listed = client.get(f"{API}/me/bookmarks", headers=as_user(USER_B)).json()["data"]["items"]
    assert [item["post"]["bookmarked"] for item in listed] == [True]


@pytest.mark.parametrize("q", ["a", " a ", "a\x07b", "x" * 51])
def test_search_query_validation(client, q):
    response = client.get(f"{API}/search/anonymous-posts", params={"q": q}, headers=as_user(USER_B))
    assert response.status_code == 400


# ---------------------------------------------------------------- FR-COM-003 reports


def report(client, user=USER_B, key="report-key-0001", **payload):
    body = {"target_type": "anonymous_post", "target_id": "post-1", "reason": "spam", **payload}
    return client.post(f"{API}/reports", json=body, headers=as_user(user, key))


def test_report_reason_enum_only_and_receipt_has_no_author(client, store):
    created = report(client)
    assert created.status_code == 201
    data = created.json()["data"]
    assert data["status"] == "submitted" and data["reason"] == "spam"
    assert set(data) == {"id", "target_type", "target_id", "reason", "status", "created_at"}
    assert not leaks_identity(created.json())
    assert report(client, key="report-key-0002", detail="자유 서술").status_code == 400
    assert report(client, key="report-key-0003", reason="custom").status_code == 400
    assert len(store.reports) == 1


def test_report_duplicates_self_reports_and_replays(client, store):
    first = report(client).json()["data"]
    replay = report(client)
    assert replay.status_code == 201 and replay.headers["Idempotent-Replayed"] == "true"
    assert replay.json()["data"]["id"] == first["id"]
    assert report(client, key="report-key-0001", reason="abuse").status_code == 409
    assert report(client, key="report-key-0002").status_code == 409  # one per reporter+target
    assert report(client, user=USER_A, key="report-key-0004").status_code == 409  # own post
    assert report(client, key="report-key-0005", target_id="missing").status_code == 404
    assert len(store.reports) == 1 and len(store.claims) == 1


def test_comment_report_and_reporter_scoped_list(client, store):
    cid = comment(client, user=USER_C).json()["data"]["id"]
    assert report(client, target_type="anonymous_comment", target_id=cid).status_code == 201
    assert (
        report(
            client,
            user=USER_C,
            key="report-key-0009",
            target_type="anonymous_comment",
            target_id=cid,
        ).status_code
        == 409
    )
    mine = client.get(f"{API}/me/reports", headers=as_user(USER_B)).json()["data"]["items"]
    assert [item["target_id"] for item in mine] == [cid]
    assert client.get(f"{API}/me/reports", headers=as_user(USER_A)).json()["data"]["items"] == []


def test_report_failure_rolls_back_claim(client, store):
    store.fail_on = "insert_report"
    failed = report(client)
    assert failed.status_code == 500 and failed.headers["Cache-Control"] == "private, no-store"
    assert store.claims == {} and store.reports == {}
    assert report(client).status_code == 201 and len(store.reports) == 1


# ---------------------------------------------------------------- FR-COM-006 groups


def test_group_create_is_user_demo_with_demo_policy(client, store):
    created = make_group(client)
    assert created.status_code == 201
    data = created.json()["data"]
    assert data["source"] == {"kind": "USER_DEMO", "url": None, "checked_at": None}
    assert data["origin"] == "member_created" and data["policy_basis"] == "DEMO_DESIGN_DEFAULT"
    assert data["leader"] == {"display_name": NAMES[USER_A]}
    assert data["my_membership"]["role"] == "leader" and data["member_count"] == 1
    assert USER_A not in json.dumps(created.json())
    replay = make_group(client)
    assert replay.headers["Idempotent-Replayed"] == "true" and len(store.groups) == 1
    assert make_group(client, name="다른 이름").status_code == 409


@pytest.mark.parametrize(
    "extra",
    [
        {"member_count": 1},
        {"source": {"kind": "OFFICIAL_PUBLIC"}},
        {"origin": "catalog"},
        {"capacity": 31},
        {"capacity": 1},
        {"name": "x"},
    ],
)
def test_group_create_rejects_server_owned_fields_and_bounds(client, extra):
    assert make_group(client, **extra).status_code == 400


def test_approval_join_flow_and_leader_only_scope(client, store):
    gid = make_group(client).json()["data"]["id"]
    joined = client.post(
        f"{API}/groups/{gid}/join-requests", headers=as_user(USER_B, "join-key-0001")
    )
    assert joined.status_code == 201 and joined.json()["data"]["status"] == "pending"
    assert (
        client.post(
            f"{API}/groups/{gid}/join-requests", headers=as_user(USER_B, "join-key-0002")
        ).status_code
        == 409
    )
    assert (
        client.get(f"{API}/groups/{gid}/join-requests", headers=as_user(USER_B)).status_code == 404
    )
    pending = client.get(f"{API}/groups/{gid}/join-requests", headers=as_user(USER_A)).json()[
        "data"
    ]["items"]
    assert pending[0]["applicant"] == {"display_name": NAMES[USER_B]}
    assert USER_B not in json.dumps(pending)
    mid = pending[0]["id"]
    decision = f"{API}/groups/{gid}/join-requests/{mid}/decision"
    assert (
        client.post(
            decision, json={"decision": "approve", "revision": 1}, headers=as_user(USER_B)
        ).status_code
        == 404
    )
    other = make_group(client, user=USER_C, key="group-key-0002").json()["data"]["id"]
    assert (
        client.post(
            f"{API}/groups/{other}/join-requests/{mid}/decision",
            json={"decision": "approve", "revision": 1},
            headers=as_user(USER_C),
        ).status_code
        == 404
    )
    approved = client.post(
        decision, json={"decision": "approve", "revision": 1}, headers=as_user(USER_A)
    )
    assert approved.status_code == 200 and approved.json()["data"]["status"] == "active"
    assert (
        client.post(
            decision, json={"decision": "approve", "revision": 2}, headers=as_user(USER_A)
        ).status_code
        == 409
    )
    group = client.get(f"{API}/groups/{gid}", headers=as_user(USER_B)).json()["data"]
    assert group["member_count"] == 2 and group["my_membership"]["status"] == "active"


def test_stale_decision_revision_is_409(client, store):
    gid = make_group(client).json()["data"]["id"]
    mid = client.post(
        f"{API}/groups/{gid}/join-requests", headers=as_user(USER_B, "join-key-0001")
    ).json()["data"]["id"]
    stale = client.post(
        f"{API}/groups/{gid}/join-requests/{mid}/decision",
        json={"decision": "reject", "revision": 7},
        headers=as_user(USER_A),
    )
    assert stale.status_code == 409 and store.memberships[mid].status == "pending"


def test_approval_rechecks_the_applicants_current_participation(client, store):
    gid = make_group(client).json()["data"]["id"]
    mid = client.post(
        f"{API}/groups/{gid}/join-requests", headers=as_user(USER_B, "join-key-0001")
    ).json()["data"]["id"]
    decision = f"{API}/groups/{gid}/join-requests/{mid}/decision"
    store.participation[USER_B] = False  # revoked after requesting
    refused = client.post(
        decision, json={"decision": "approve", "revision": 1}, headers=as_user(USER_A)
    )
    assert refused.status_code == 409
    assert store.memberships[mid].status == "pending" and store.groups[gid].member_count == 1
    assert USER_B not in json.dumps(refused.json())
    rejected = client.post(
        decision, json={"decision": "reject", "revision": 1}, headers=as_user(USER_A)
    )
    assert rejected.status_code == 200 and store.memberships[mid].status == "rejected"


def test_rejected_cannot_rerequest_and_capacity_is_enforced(client, store):
    gid = make_group(client, capacity=2, join_mode="open").json()["data"]["id"]
    assert (
        client.post(
            f"{API}/groups/{gid}/join-requests", headers=as_user(USER_B, "join-key-0001")
        ).json()["data"]["status"]
        == "active"
    )
    full = client.post(
        f"{API}/groups/{gid}/join-requests", headers=as_user(USER_C, "join-key-0001")
    )
    assert full.status_code == 409 and store.groups[gid].member_count == 2
    approval = make_group(client, key="group-key-0003").json()["data"]["id"]
    mid = client.post(
        f"{API}/groups/{approval}/join-requests", headers=as_user(USER_C, "join-key-0002")
    ).json()["data"]["id"]
    client.post(
        f"{API}/groups/{approval}/join-requests/{mid}/decision",
        json={"decision": "reject", "revision": 1},
        headers=as_user(USER_A),
    )
    again = client.post(
        f"{API}/groups/{approval}/join-requests", headers=as_user(USER_C, "join-key-0003")
    )
    assert again.status_code == 409


def test_leave_and_rejoin_reuses_row_and_replays(client, store):
    gid = make_group(client, join_mode="open").json()["data"]["id"]
    joined = client.post(
        f"{API}/groups/{gid}/join-requests", headers=as_user(USER_B, "join-key-0001")
    ).json()["data"]
    assert (
        client.post(
            f"{API}/groups/{gid}/membership/leave", json={"revision": 1}, headers=as_user(USER_A)
        ).status_code
        == 409
    )
    assert (
        client.post(
            f"{API}/groups/{gid}/membership/leave", json={"revision": 9}, headers=as_user(USER_B)
        ).status_code
        == 409
    )
    left = client.post(
        f"{API}/groups/{gid}/membership/leave", json={"revision": 1}, headers=as_user(USER_B)
    )
    assert left.json()["data"]["status"] == "left" and store.groups[gid].member_count == 1
    rejoin = client.post(
        f"{API}/groups/{gid}/join-requests", headers=as_user(USER_B, "join-key-0002")
    )
    assert (
        rejoin.json()["data"]["id"] == joined["id"] and rejoin.json()["data"]["status"] == "active"
    )
    replay = client.post(
        f"{API}/groups/{gid}/join-requests", headers=as_user(USER_B, "join-key-0002")
    )
    assert (
        replay.headers["Idempotent-Replayed"] == "true"
        and replay.json()["data"]["id"] == joined["id"]
    )
    assert store.groups[gid].member_count == 2


@pytest.mark.parametrize(
    "source,kind,url",
    [
        ("official_ok", "OFFICIAL_PUBLIC", "https://www.dit.ac.kr/kr/index.php?pCode=example"),
        ("official_no_url", "UNKNOWN", None),
        ("official_http", "UNKNOWN", None),
        ("official_creds", "UNKNOWN", None),
        ("official_future", "UNKNOWN", None),
        ("official_naive", "UNKNOWN", None),
        ("demo_with_url", "DEMO", None),
        ("unknown", "UNKNOWN", None),
    ],
)
def test_catalog_source_is_normalized_fail_closed(client, store, source, kind, url):
    store.add_catalog_group("club-1", SOURCES[source])
    data = client.get(f"{API}/groups/club-1", headers=as_user(USER_B)).json()["data"]
    assert data["source"]["kind"] == kind and data["source"]["url"] == url
    assert (data["source"]["checked_at"] is not None) == (kind == "OFFICIAL_PUBLIC")
    joined = client.post(
        f"{API}/groups/club-1/join-requests", headers=as_user(USER_B, "join-key-0001")
    )
    # Official/unknown club membership follows unapproved school rules: info only.
    assert joined.status_code == (201 if source == "demo_with_url" else 409)


def test_group_list_filters_and_query_validation(client):
    make_group(client)
    make_group(client, key="group-key-0002", kind="club", name="가상 밴드 동아리")
    clubs = client.get(f"{API}/groups?kind=club", headers=as_user(USER_B)).json()["data"]["items"]
    assert [g["name"] for g in clubs] == ["가상 밴드 동아리"]
    found = client.get(f"{API}/groups", params={"q": "알고리즘"}, headers=as_user(USER_B)).json()[
        "data"
    ]["items"]
    assert len(found) == 1 and found[0]["my_membership"] is None
    assert client.get(f"{API}/groups?q=a", headers=as_user(USER_B)).status_code == 400
    assert client.get(f"{API}/groups?kind=official", headers=as_user(USER_B)).status_code == 400


# ---------------------------------------------------------------- FR-COM-007 team space


def space_post(client, gid, user=USER_A, key="space-key-0001", body="가상 회의 기록"):
    return client.post(
        f"{API}/groups/{gid}/space/posts", json={"body": body}, headers=as_user(user, key)
    )


def test_space_is_members_only_and_revocation_applies(client, store):
    gid = make_group(client).json()["data"]["id"]
    assert space_post(client, gid).status_code == 201
    for user in (USER_B, USER_C):
        assert (
            client.get(f"{API}/groups/{gid}/space/posts", headers=as_user(user)).status_code == 404
        )
        assert space_post(client, gid, user=user).status_code == 404
    mid = client.post(
        f"{API}/groups/{gid}/join-requests", headers=as_user(USER_B, "join-key-0001")
    ).json()["data"]["id"]
    assert (
        client.get(f"{API}/groups/{gid}/space/posts", headers=as_user(USER_B)).status_code == 404
    )  # pending
    client.post(
        f"{API}/groups/{gid}/join-requests/{mid}/decision",
        json={"decision": "approve", "revision": 1},
        headers=as_user(USER_A),
    )
    items = client.get(f"{API}/groups/{gid}/space/posts", headers=as_user(USER_B)).json()["data"][
        "items"
    ]
    assert items[0]["author"] == {"display_name": NAMES[USER_A]} and items[0]["is_mine"] is False
    assert space_post(client, gid, user=USER_B, key="space-key-0002").status_code == 201
    client.post(
        f"{API}/groups/{gid}/membership/leave", json={"revision": 2}, headers=as_user(USER_B)
    )
    assert client.get(f"{API}/groups/{gid}/space/posts", headers=as_user(USER_B)).status_code == 404
    # A replay after losing membership is refused before the stored record is consulted.
    assert space_post(client, gid, user=USER_B, key="space-key-0002").status_code == 404


def test_space_post_delete_owner_revision_tombstone(client, store):
    gid = make_group(client, join_mode="open").json()["data"]["id"]
    client.post(f"{API}/groups/{gid}/join-requests", headers=as_user(USER_B, "join-key-0001"))
    pid = space_post(client, gid).json()["data"]["id"]
    url = f"{API}/groups/{gid}/space/posts/{pid}"
    assert client.delete(f"{url}?revision=1", headers=as_user(USER_B)).status_code == 404
    assert client.delete(f"{url}?revision=5", headers=as_user(USER_A)).status_code == 409
    assert client.delete(f"{url}?revision=1", headers=as_user(USER_A)).status_code == 200
    assert store.space_posts[pid].body == "" and store.space_posts[pid].status == "deleted"
    assert space_post(client, gid).status_code == 404  # replay of deleted post
    assert len(store.space_posts) == 1


# ---------------------------------------------------------------- cross-zone (TC-V1-X02)


def test_anonymous_and_real_name_zones_share_no_identifier(client):
    anonymous = comment(client, user=USER_A, key="comment-key-0100").json()
    gid = make_group(client, user=USER_A).json()["data"]["id"]
    real = space_post(client, gid, user=USER_A).json()
    anon_text = json.dumps(anonymous, ensure_ascii=False)
    real_text = json.dumps(real, ensure_ascii=False)
    assert NAMES[USER_A] in real_text and NAMES[USER_A] not in anon_text
    assert USER_A not in anon_text and USER_A not in real_text
    assert anonymous["data"]["id"] not in real_text and real["data"]["id"] not in anon_text


def test_naive_server_clock_fails_closed(store):
    from datetime import datetime

    deps = CollaborationDependencies(
        actor=header_actor, store=lambda: store, clock=lambda: datetime(2026, 10, 30)
    )
    naive = mount(create_collaboration_router(deps))
    response = comment(naive)
    assert response.status_code == 500 and store.comments == {}
