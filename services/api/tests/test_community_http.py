"""HTTP contract tests for the community router with TEST-ONLY in-memory fakes.

The fakes stand in for repositories the DB owner has not delivered; they are not production
storage. ``X-Test-Actor`` is a test-only stand-in for the auth owner's verified actor provider.
"""

import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from itertools import count

import pytest
from fastapi import Header
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.factory import create_app
from app.features.community import CommunityActor, CommunityDependencies, create_community_router
from app.features.community.domain import PostStatus
from app.features.community.service import _public_row

NOW = datetime(2026, 10, 30, 3, 0, tzinfo=UTC)
PREFIX = "/api/v1"
ACTORS = {
    "a": CommunityActor("user-a-secret-id", True),
    "b": CommunityActor("user-b-secret-id", True),
    "blocked": CommunityActor("user-x-secret-id", False),
    # Same user as "a" after the server revoked community access.
    "a-revoked": CommunityActor("user-a-secret-id", False),
}
NAMES = {"user-a-secret-id": "가상학생A", "user-b-secret-id": "가상학생B"}
VISIBLE_OPPORTUNITIES = {"o1"}  # "o-hidden" exists for its owner but is not visible to callers
_keys = count(1)


class FakePosts:
    def __init__(self):
        self.private = {}
        self.public = {}
        self.claims = {}

    def create(self, post, claim):
        # Claim, private row and projection are one unit; an existing claim writes nothing.
        if claim.namespace in self.claims:
            return self.claims[claim.namespace]
        self.claims[claim.namespace] = claim
        self.private[post.id] = post
        self.public[post.id] = _public_row(post)
        return claim

    def get_private(self, post_id):
        return self.private.get(post_id)

    def update(self, post, expected_revision):
        if self.private[post.id].revision != expected_revision:
            return False
        self.private[post.id] = post
        if post.status is PostStatus.ACTIVE:
            self.public[post.id] = _public_row(post)
        else:
            self.public.pop(post.id, None)
        return True

    def get_public(self, post_id):
        return self.public.get(post_id)

    def list_public(self, *, limit, offset):
        rows = sorted(self.public.values(), key=lambda r: r.created_at, reverse=True)
        return rows[offset : offset + limit]

    def owned_post_ids(self, author_id, post_ids):
        return {i for i in post_ids if self.private[i].author_id == author_id}


class FakeRecruitments:
    def __init__(self):
        self.rows = {}
        self.claims = {}

    def create(self, recruitment, claim):
        if claim.namespace in self.claims:
            return self.claims[claim.namespace]
        self.claims[claim.namespace] = claim
        self.rows[recruitment.id] = recruitment
        return claim

    def get(self, recruitment_id):
        return self.rows.get(recruitment_id)

    def update(self, recruitment, expected_revision):
        if self.rows[recruitment.id].revision != expected_revision:
            return False
        self.rows[recruitment.id] = recruitment
        return True

    def list(self, *, limit, offset):
        return list(self.rows.values())[offset : offset + limit]


class FakeProfiles:
    def __init__(self):
        self.calls = 0

    def display_names(self, user_ids):
        self.calls += 1
        return {uid: NAMES[uid] for uid in user_ids if uid in NAMES}


class FakeOpportunities:
    def __init__(self):
        self.calls = []

    def is_linkable(self, actor_id, opportunity_id):
        self.calls.append((actor_id, opportunity_id))
        return opportunity_id in VISIBLE_OPPORTUNITIES


class Clock:
    def __init__(self):
        self.now = NOW

    def __call__(self):
        return self.now


def fake_actor(x_test_actor: str | None = Header(default=None)) -> CommunityActor | None:
    return ACTORS.get(x_test_actor) if x_test_actor else None


@pytest.fixture
def env():
    posts, recruitments, profiles, clock = FakePosts(), FakeRecruitments(), FakeProfiles(), Clock()
    ids = count(1)
    deps = CommunityDependencies(
        actor=fake_actor,
        posts=lambda: posts,
        recruitments=lambda: recruitments,
        profiles=lambda: profiles,
        opportunities=FakeOpportunities,
        clock=clock,
        id_factory=lambda: f"id-{next(ids)}",
    )
    app = create_app(Settings(environment="test"))
    app.include_router(create_community_router(deps), prefix=PREFIX)
    with TestClient(app) as client:
        yield client, posts, recruitments, profiles, clock


CREATE_PATHS = {"/anonymous-posts", "/recruitments"}


def call(client, method, path, who=None, key=None, **kwargs):
    """``key`` defaults to a fresh Idempotency-Key on create POSTs; pass ``""`` to omit it."""
    headers = {"X-Test-Actor": who} if who else {}
    if method == "POST" and path in CREATE_PATHS and key is None:
        key = f"auto-key-{next(_keys)}"
    if key:
        headers["Idempotency-Key"] = key
    return client.request(method, PREFIX + path, headers=headers, **kwargs)


def assert_no_identity(payload):
    text = json.dumps(payload, ensure_ascii=False)
    for secret in ("user-a-secret-id", "user-b-secret-id", "가상학생A", "가상학생B"):
        assert secret not in text
    for key in ("author", "author_id", "user_id", "owner_id", "owner", "email", "department"):
        assert f'"{key}"' not in text


def future(days=2):
    return (NOW + timedelta(days=days)).isoformat()


def new_recruitment(**overrides):
    body = dict(
        title="공모전 팀원 모집",
        body="백엔드 구해요",
        field="개발",
        roles=["백엔드", "디자인"],
        capacity=3,
        deadline_at=future(),
    )
    body.update(overrides)
    return body


# ------------------------------------------------------------------- fail-closed defaults


@pytest.mark.parametrize(
    "method,path,body",
    [
        ("GET", "/anonymous-posts", None),
        ("POST", "/anonymous-posts", {"title": "제목입니다", "body": "본문"}),
        ("DELETE", "/anonymous-posts/id-1?revision=1", None),
        ("GET", "/recruitments", None),
        ("POST", "/recruitments/id-1/close", {"revision": 1}),
    ],
)
def test_default_router_fails_closed_without_auth_and_db(method, path, body):
    app = create_app(Settings(environment="test"))
    app.include_router(create_community_router(), prefix=PREFIX)
    with TestClient(app) as client:
        response = client.request(method, PREFIX + path, json=body)
    assert response.status_code == 503
    assert response.json()["code"] == "UNAVAILABLE"
    assert response.json()["retryable"] is True


def test_default_export_is_fail_closed_router():
    from app.features.community import router

    app = create_app(Settings(environment="test"))
    app.include_router(router, prefix=PREFIX)
    with TestClient(app) as client:
        assert client.get(PREFIX + "/recruitments").status_code == 503


@pytest.mark.parametrize("path", ["/anonymous-posts", "/recruitments"])
def test_unauthenticated_and_unapproved_are_rejected(env, path):
    client = env[0]
    assert call(client, "GET", path).status_code == 401
    assert call(client, "GET", path, who="blocked").status_code == 403
    # Auth is resolved before body validation, so anonymous callers learn nothing about schema.
    assert call(client, "POST", path, json={}).status_code == 401


def test_auth_is_checked_before_storage():
    def broken_storage():
        raise AssertionError("storage must not be touched for anonymous callers")

    deps = CommunityDependencies(actor=fake_actor, posts=broken_storage)
    app = create_app(Settings(environment="test"))
    app.include_router(create_community_router(deps), prefix=PREFIX)
    with TestClient(app) as client:
        response = client.get(PREFIX + "/anonymous-posts")
    assert response.status_code == 401


def test_openapi_contract_has_no_anonymous_identity():
    app = create_app(Settings(environment="test"))
    app.include_router(create_community_router(), prefix=PREFIX)
    schema = app.openapi()
    assert {
        "/api/v1/anonymous-posts",
        "/api/v1/anonymous-posts/{post_id}",
        "/api/v1/recruitments",
        "/api/v1/recruitments/{recruitment_id}",
        "/api/v1/recruitments/{recruitment_id}/close",
    } <= set(schema["paths"])
    components = schema["components"]["schemas"]
    public_post = set(components["AnonymousPostPublic"]["properties"])
    assert public_post.isdisjoint({"author_id", "user_id", "owner", "email", "department"})
    assert set(components["AnonymousPostCreate"]["properties"]) == {"title", "body"}
    assert "owner_id" not in components["RecruitmentCreate"]["properties"]


# ------------------------------------------------------------------- FR-COM-001 / TC-V1-COM-001


def test_anonymous_post_crud_and_anonymity(env):
    client, posts, *_ = env
    created = call(
        client, "POST", "/anonymous-posts", "a", json={"title": "  첫 글  ", "body": "안녕"}
    )
    assert created.status_code == 201
    data = created.json()["data"]
    assert (data["title"], data["display_name"], data["is_mine"]) == ("첫 글", "익명", True)
    assert created.json()["resource_version"] == 1
    assert_no_identity(created.json())
    assert posts.private["id-1"].author_id == "user-a-secret-id"

    seen_by_b = call(client, "GET", "/anonymous-posts/id-1", "b").json()
    assert seen_by_b["data"]["is_mine"] is False
    listing = call(client, "GET", "/anonymous-posts", "b").json()
    assert [item["id"] for item in listing["data"]["items"]] == ["id-1"]
    assert_no_identity(seen_by_b)
    assert_no_identity(listing)

    updated = call(
        client, "PATCH", "/anonymous-posts/id-1", "a", json={"revision": 1, "body": "수정됨"}
    )
    assert updated.status_code == 200
    assert (updated.json()["data"]["body"], updated.json()["resource_version"]) == ("수정됨", 2)
    assert updated.json()["data"]["title"] == "첫 글"

    deleted = call(client, "DELETE", "/anonymous-posts/id-1?revision=2", "a")
    assert deleted.json()["data"] == {"id": "id-1", "deleted": True}
    assert call(client, "GET", "/anonymous-posts/id-1", "a").status_code == 404
    assert call(client, "GET", "/anonymous-posts", "a").json()["data"]["items"] == []
    assert posts.private["id-1"].status is PostStatus.DELETED


def test_other_user_cannot_modify_post(env):
    client = env[0]
    call(client, "POST", "/anonymous-posts", "a", json={"title": "A의 글", "body": "본문"})
    patch = call(client, "PATCH", "/anonymous-posts/id-1", "b", json={"revision": 1, "body": "x"})
    delete = call(client, "DELETE", "/anonymous-posts/id-1?revision=1", "b")
    assert (patch.status_code, delete.status_code) == (404, 404)
    assert call(client, "GET", "/anonymous-posts/id-1", "b").json()["data"]["body"] == "본문"


@pytest.mark.parametrize(
    "payload",
    [
        {"title": "제목입니다", "body": "본문", "author_id": "user-b-secret-id"},
        {"title": "제목입니다", "body": "본문", "user_id": "user-b-secret-id"},
        {"title": "제목입니다", "body": "본문", "is_mine": False},
        {"title": "가", "body": "본문"},
        {"title": "제목입니다", "body": ""},
        {"title": "제목입니다", "body": "x" * 5001},
    ],
)
def test_post_create_rejects_invalid_or_injected(env, payload):
    client, posts, *_ = env
    response = call(client, "POST", "/anonymous-posts", "a", json=payload)
    assert response.status_code == 400
    assert response.json()["code"] == "VALIDATION"
    assert "user-b-secret-id" not in response.text
    assert posts.private == {}


def test_post_revision_conflict(env):
    client = env[0]
    call(client, "POST", "/anonymous-posts", "a", json={"title": "제목입니다", "body": "본문"})
    call(client, "PATCH", "/anonymous-posts/id-1", "a", json={"revision": 1, "body": "v2"})
    stale = call(client, "PATCH", "/anonymous-posts/id-1", "a", json={"revision": 1, "body": "v3"})
    assert stale.status_code == 409
    assert call(client, "DELETE", "/anonymous-posts/id-1?revision=1", "a").status_code == 409


def test_hidden_post_is_not_public(env):
    client, posts, *_ = env
    call(client, "POST", "/anonymous-posts", "a", json={"title": "제목입니다", "body": "본문"})
    hidden = replace(posts.private["id-1"], status=PostStatus.HIDDEN, revision=2)
    posts.update(hidden, 1)
    assert call(client, "GET", "/anonymous-posts/id-1", "b").status_code == 404
    patch = call(client, "PATCH", "/anonymous-posts/id-1", "a", json={"revision": 2, "body": "x"})
    assert patch.status_code == 404


def test_script_is_stored_as_text_not_html(env):
    client = env[0]
    payload = {"title": "<b>제목</b>", "body": "<script>alert(1)</script>"}
    response = call(client, "POST", "/anonymous-posts", "a", json=payload)
    assert response.headers["content-type"].startswith("application/json")
    assert response.json()["data"]["body"] == "<script>alert(1)</script>"


def test_post_pagination(env):
    client, _, _, _, clock = env
    for index in range(3):
        clock.now = NOW + timedelta(minutes=index)
        call(client, "POST", "/anonymous-posts", "a", json={"title": f"글{index}", "body": "b"})
    first = call(client, "GET", "/anonymous-posts?limit=2", "b").json()["data"]
    assert ([i["id"] for i in first["items"]], first["has_more"]) == (["id-3", "id-2"], True)
    rest = call(client, "GET", "/anonymous-posts?limit=2&offset=2", "b").json()["data"]
    assert ([i["id"] for i in rest["items"]], rest["has_more"]) == (["id-1"], False)
    assert call(client, "GET", "/anonymous-posts?limit=51", "b").status_code == 400


@pytest.mark.parametrize("bad_id", ["..%2F..", "a" * 65, "id%20x"])
def test_path_ids_are_validated(env, bad_id):
    assert call(env[0], "GET", f"/anonymous-posts/{bad_id}", "a").status_code in {400, 404}


# ------------------------------------------------------------------- FR-COM-004 / TC-V1-COM-004


def test_recruitment_crud_close_and_profile_only(env):
    client, _, recruitments, profiles, _ = env
    created = call(client, "POST", "/recruitments", "a", json=new_recruitment(opportunity_id="o1"))
    assert created.status_code == 201
    data = created.json()["data"]
    assert data["owner"] == {"display_name": "가상학생A"}
    assert (data["status"], data["capacity"], data["accepted_count"]) == ("open", 3, 0)
    assert data["is_mine"] is True and data["opportunity_id"] == "o1"
    assert "user-a-secret-id" not in created.text and "owner_id" not in created.text

    seen = call(client, "GET", "/recruitments/id-1", "b").json()["data"]
    assert (seen["is_mine"], seen["owner"]["display_name"]) == (False, "가상학생A")

    patch = call(client, "PATCH", "/recruitments/id-1", "a", json={"revision": 1, "capacity": 5})
    assert (patch.json()["data"]["capacity"], patch.json()["resource_version"]) == (5, 2)

    closed = call(client, "POST", "/recruitments/id-1/close", "a", json={"revision": 2})
    assert closed.json()["data"]["status"] == "closed"
    again = call(client, "POST", "/recruitments/id-1/close", "a", json={"revision": 3})
    assert again.status_code == 409
    after_close = call(
        client, "PATCH", "/recruitments/id-1", "a", json={"revision": 3, "body": "x"}
    )
    assert after_close.status_code == 409
    assert recruitments.rows["id-1"].owner_id == "user-a-secret-id"

    calls_before = profiles.calls
    call(client, "POST", "/recruitments", "b", json=new_recruitment())
    listing = call(client, "GET", "/recruitments", "a").json()["data"]["items"]
    assert profiles.calls == calls_before + 2  # one per create + one batched list lookup
    assert [(i["owner"]["display_name"], i["is_mine"]) for i in listing] == [
        ("가상학생A", True),
        ("가상학생B", False),
    ]


def test_other_user_cannot_change_recruitment(env):
    client = env[0]
    call(client, "POST", "/recruitments", "a", json=new_recruitment())
    patch = call(client, "PATCH", "/recruitments/id-1", "b", json={"revision": 1, "title": "탈취"})
    close = call(client, "POST", "/recruitments/id-1/close", "b", json={"revision": 1})
    assert (patch.status_code, close.status_code) == (404, 404)


@pytest.mark.parametrize(
    "overrides,status",
    [
        ({"capacity": 1}, 400),
        ({"capacity": 21}, 400),
        ({"owner_id": "user-b-secret-id"}, 400),
        ({"status": "closed"}, 400),
        ({"deadline_at": (NOW - timedelta(minutes=1)).isoformat()}, 400),
        ({"deadline_at": NOW.isoformat()}, 400),
        ({"roles": ["백엔드", "백엔드"]}, 400),
    ],
)
def test_recruitment_create_validation(env, overrides, status):
    client, _, recruitments, *_ = env
    response = call(client, "POST", "/recruitments", "a", json=new_recruitment(**overrides))
    assert response.status_code == status
    assert recruitments.rows == {}


def test_recruitment_deadline_judged_by_server_clock(env):
    client, *_, clock = env
    call(client, "POST", "/recruitments", "a", json=new_recruitment(deadline_at=future(1)))
    clock.now = NOW + timedelta(days=1)
    assert call(client, "GET", "/recruitments/id-1", "b").json()["data"]["status"] == "closed"
    patch = call(client, "PATCH", "/recruitments/id-1", "a", json={"revision": 1, "body": "x"})
    assert patch.status_code == 409
    past = call(
        client,
        "PATCH",
        "/recruitments/id-1",
        "a",
        json={"revision": 1, "deadline_at": future(3)},
    )
    assert past.status_code == 409


def test_capacity_cannot_drop_below_team(env):
    client, _, recruitments, *_ = env
    call(client, "POST", "/recruitments", "a", json=new_recruitment(capacity=4))
    recruitments.rows["id-1"] = replace(recruitments.rows["id-1"], accepted_count=2)
    too_small = call(
        client, "PATCH", "/recruitments/id-1", "a", json={"revision": 1, "capacity": 2}
    )
    assert too_small.status_code == 409
    exact = call(client, "PATCH", "/recruitments/id-1", "a", json={"revision": 1, "capacity": 3})
    assert exact.status_code == 200


def test_recruitment_revision_conflict(env):
    client = env[0]
    call(client, "POST", "/recruitments", "a", json=new_recruitment())
    call(client, "PATCH", "/recruitments/id-1", "a", json={"revision": 1, "body": "v2"})
    stale = call(client, "PATCH", "/recruitments/id-1", "a", json={"revision": 1, "body": "v3"})
    assert stale.status_code == 409


def test_anonymous_and_recruitment_are_not_linked(env):
    """TC-V1-X02: A's anonymous post and real-name recruitment share no public identifier."""
    client = env[0]
    post = call(client, "POST", "/anonymous-posts", "a", json={"title": "익명 글", "body": "b"})
    rec = call(client, "POST", "/recruitments", "a", json=new_recruitment())
    post_view = call(client, "GET", f"/anonymous-posts/{post.json()['data']['id']}", "b").json()
    rec_view = call(client, "GET", f"/recruitments/{rec.json()['data']['id']}", "b").json()
    assert_no_identity(post_view)
    shared = set(json.dumps(post_view["data"]).split('"')) & {
        str(value) for value in rec_view["data"]["owner"].values()
    }
    assert shared == set()


# ------------------------------------------------------------------- idempotent creates


def test_same_key_and_body_replays_the_same_post(env):
    """Review finding: two POSTs with one Idempotency-Key must not create two posts."""
    client, posts, *_ = env
    body = {"title": "중복 클릭", "body": "본문"}
    first = call(client, "POST", "/anonymous-posts", "a", key="k-1", json=body)
    second = call(client, "POST", "/anonymous-posts", "a", key="k-1", json=body)
    assert (first.status_code, second.status_code) == (201, 201)
    assert first.json()["data"]["id"] == second.json()["data"]["id"] == "id-1"
    assert "Idempotent-Replayed" not in first.headers
    assert second.headers["Idempotent-Replayed"] == "true"
    assert len(posts.private) == len(posts.public) == 1
    assert_no_identity(second.json())


def test_same_key_and_body_replays_the_same_recruitment(env):
    client, _, recruitments, *_ = env
    payload = new_recruitment()
    first = call(client, "POST", "/recruitments", "a", key="k-1", json=payload)
    second = call(client, "POST", "/recruitments", "a", key="k-1", json=payload)
    assert first.json()["data"]["id"] == second.json()["data"]["id"]
    assert second.headers["Idempotent-Replayed"] == "true"
    assert len(recruitments.rows) == 1


def test_normalized_body_is_the_same_request(env):
    client, posts, *_ = env
    call(client, "POST", "/anonymous-posts", "a", key="k", json={"title": "제목", "body": "b"})
    retry = call(
        client, "POST", "/anonymous-posts", "a", key="k", json={"title": " 제목 ", "body": "b"}
    )
    assert retry.headers["Idempotent-Replayed"] == "true"
    assert len(posts.private) == 1


@pytest.mark.parametrize(
    "path,first,second",
    [
        ("/anonymous-posts", {"title": "제목", "body": "a"}, {"title": "제목", "body": "b"}),
        ("/recruitments", new_recruitment(), new_recruitment(capacity=4)),
    ],
)
def test_same_key_different_body_is_conflict(env, path, first, second):
    client, posts, recruitments, *_ = env
    assert call(client, "POST", path, "a", key="k", json=first).status_code == 201
    conflict = call(client, "POST", path, "a", key="k", json=second)
    assert conflict.status_code == 409
    assert conflict.json()["code"] == "CONFLICT"
    assert len(posts.private) + len(recruitments.rows) == 1


def test_key_scope_is_actor_method_and_path(env):
    client, posts, recruitments, *_ = env
    body = {"title": "제목", "body": "b"}
    a = call(client, "POST", "/anonymous-posts", "a", key="shared", json=body).json()["data"]
    b = call(client, "POST", "/anonymous-posts", "b", key="shared", json=body).json()["data"]
    rec = call(client, "POST", "/recruitments", "a", key="shared", json=new_recruitment())
    assert a["id"] != b["id"]
    assert (a["is_mine"], b["is_mine"]) == (True, True)
    assert rec.status_code == 201 and "Idempotent-Replayed" not in rec.headers
    assert (len(posts.private), len(recruitments.rows)) == (2, 1)


@pytest.mark.parametrize("key", ["", "has space", "한글키".encode(), "x" * 129])
@pytest.mark.parametrize("path", ["/anonymous-posts", "/recruitments"])
def test_create_requires_a_valid_key(env, path, key):
    client, posts, recruitments, *_ = env
    body = new_recruitment() if path == "/recruitments" else {"title": "제목", "body": "b"}
    headers = {"X-Test-Actor": "a"}
    if key:
        headers["Idempotency-Key"] = key
    response = client.post(PREFIX + path, headers=headers, json=body)
    assert response.status_code == 400
    assert response.json()["code"] == "VALIDATION"
    assert posts.private == {} and recruitments.rows == {}


def test_missing_key_still_answers_401_first(env):
    assert call(env[0], "POST", "/anonymous-posts", key="", json={}).status_code == 401


def test_replay_rechecks_current_permission(env):
    client, posts, *_ = env
    body = {"title": "제목", "body": "b"}
    call(client, "POST", "/anonymous-posts", "a", key="k", json=body)
    revoked = call(client, "POST", "/anonymous-posts", "a-revoked", key="k", json=body)
    assert revoked.status_code == 403
    assert "id-1" not in revoked.text
    assert len(posts.private) == 1


def test_replay_reads_current_visibility_and_revision(env):
    client, posts, *_ = env
    body = {"title": "제목", "body": "b"}
    call(client, "POST", "/anonymous-posts", "a", key="k", json=body)
    call(client, "PATCH", "/anonymous-posts/id-1", "a", json={"revision": 1, "body": "v2"})
    replay = call(client, "POST", "/anonymous-posts", "a", key="k", json=body)
    assert (replay.json()["data"]["body"], replay.json()["resource_version"]) == ("v2", 2)
    call(client, "DELETE", "/anonymous-posts/id-1?revision=2", "a")
    gone = call(client, "POST", "/anonymous-posts", "a", key="k", json=body)
    assert gone.status_code == 404
    assert len(posts.private) == 1  # a replay never resurrects or re-creates


def test_revision_and_key_are_checked_independently(env):
    client = env[0]
    call(client, "POST", "/anonymous-posts", "a", key="k", json={"title": "제목", "body": "b"})
    call(client, "PATCH", "/anonymous-posts/id-1", "a", json={"revision": 1, "body": "v2"})
    # A key on a revisioned change does not bypass the stale-revision check.
    stale = call(
        client, "PATCH", "/anonymous-posts/id-1", "a", key="k", json={"revision": 1, "body": "v3"}
    )
    assert stale.status_code == 409
    call(client, "POST", "/recruitments", "a", key="r", json=new_recruitment())
    close = call(client, "POST", "/recruitments/id-2/close", "a", key="r", json={"revision": 1})
    assert close.json()["data"]["status"] == "closed"
    again = call(client, "POST", "/recruitments/id-2/close", "a", key="r", json={"revision": 1})
    assert again.status_code == 409


# ------------------------------------------------------------------- private caching


@pytest.mark.parametrize(
    "create_path,read_path",
    [
        ("/anonymous-posts", "/anonymous-posts"),
        ("/anonymous-posts", "/anonymous-posts/id-1"),
        ("/recruitments", "/recruitments"),
        ("/recruitments", "/recruitments/id-1"),
    ],
)
def test_per_caller_reads_are_private_no_store(env, create_path, read_path):
    client = env[0]
    body = new_recruitment() if create_path == "/recruitments" else {"title": "제목", "body": "b"}
    created = call(client, "POST", create_path, "a", json=body)
    assert created.headers["Cache-Control"] == "private, no-store"
    mine = call(client, "GET", read_path, "a")
    theirs = call(client, "GET", read_path, "b")
    for response in (mine, theirs):
        assert response.headers["Cache-Control"] == "private, no-store"

    def flag(response):
        data = response.json()["data"]
        return (data["items"][0] if "items" in data else data)["is_mine"]

    assert (flag(mine), flag(theirs)) == (True, False)


# ------------------------------------------------------------------- opportunity link seam


def _without_request_id(response):
    return {k: v for k, v in response.json().items() if k != "request_id"}


def test_opportunity_link_requires_visible_opportunity(env):
    client, _, recruitments, *_ = env
    ok = call(client, "POST", "/recruitments", "a", json=new_recruitment(opportunity_id="o1"))
    assert ok.status_code == 201 and ok.json()["data"]["opportunity_id"] == "o1"
    missing = call(client, "POST", "/recruitments", "a", json=new_recruitment(opportunity_id="no"))
    hidden = call(
        client, "POST", "/recruitments", "a", json=new_recruitment(opportunity_id="o-hidden")
    )
    assert (missing.status_code, hidden.status_code) == (400, 400)
    # Missing and hidden are indistinguishable apart from the per-request id.
    assert _without_request_id(missing) == _without_request_id(hidden)
    assert len(recruitments.rows) == 1


def test_opportunity_link_refused_without_provider():
    recruitments = FakeRecruitments()
    deps = CommunityDependencies(
        actor=fake_actor,
        recruitments=lambda: recruitments,
        profiles=FakeProfiles,
        clock=Clock(),
    )
    app = create_app(Settings(environment="test"))
    app.include_router(create_community_router(deps), prefix=PREFIX)
    with TestClient(app) as client:
        linked = call(
            client, "POST", "/recruitments", "a", json=new_recruitment(opportunity_id="o1")
        )
        plain = call(client, "POST", "/recruitments", "a", json=new_recruitment())
    assert linked.status_code == 400
    assert plain.status_code == 201 and plain.json()["data"]["opportunity_id"] is None
    assert len(recruitments.rows) == 1
