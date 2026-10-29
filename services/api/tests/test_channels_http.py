"""Router contract for the unmounted free-channel module (test-only dependency overrides).

Fail-closed 503, 401, private no-store on success and error, validation without reflection,
no approval/badge endpoints. Not a global-app, MariaDB or E2E result.
"""

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from test_channels_support import ALICE, BOB, DAVE, DEFAULT_CHANNEL, DEPT, KEY, make

from app.core.config import Settings
from app.factory import create_app
from app.features.channels import get_channels_actor, get_channels_service, router

HEADERS = {"Idempotency-Key": KEY}
CID = "00000000-0000-4000-8000-0000000000c1"
REASON = "학과 공식 학습 공동체로 운영하고 싶습니다."

ROUTES = [
    ("get", f"/departments/{DEPT}/free-channels", None),
    ("get", "/me/free-channels", None),
    ("post", "/free-channels", {"department_id": str(DEPT), "name": "x"}),
    ("get", f"/free-channels/{CID}", None),
    ("patch", f"/free-channels/{CID}", {"name": "x", "expected_revision": 1}),
    ("post", f"/free-channels/{CID}/archive", {"expected_revision": 1}),
    ("post", f"/free-channels/{CID}/join", None),
    ("post", f"/free-channels/{CID}/leave", None),
    ("post", f"/free-channels/{CID}/official-requests", {"reason": REASON}),
    ("get", "/me/official-channel-requests", None),
    ("get", f"/me/official-channel-requests/{CID}", None),
]


def build(actor=None, service=None, *, wire_actor=False, wire_service=False):
    app = create_app(Settings(environment="test"))
    app.include_router(router, prefix="/api/v1")
    if wire_actor:
        app.dependency_overrides[get_channels_actor] = lambda: actor
    if wire_service:
        app.dependency_overrides[get_channels_service] = lambda: service
    return app


@pytest.fixture
def wired():
    service, store = make()
    state = {"actor": ALICE}
    app = build(service=service, wire_service=True)
    app.dependency_overrides[get_channels_actor] = lambda: state["actor"]
    with TestClient(app) as client:
        yield client, state, store


def call(client, method, path, body=None, headers=None):
    kwargs = {"headers": headers or HEADERS}
    if body is not None:
        kwargs["json"] = body
    response = getattr(client, method)(f"/api/v1{path}", **kwargs)
    assert response.headers["Cache-Control"] == "private, no-store"
    return response


def test_global_app_does_not_mount_channels():
    app = create_app(Settings(environment="test"))
    assert not any("free-channel" in path for path in app.openapi()["paths"])
    assert not any("official-channel" in path for path in app.openapi()["paths"])


@pytest.mark.parametrize("method,path,body", ROUTES)
def test_unwired_router_fails_closed_503(method, path, body):
    with TestClient(build()) as client:
        assert call(client, method, path, body).status_code == 503


@pytest.mark.parametrize("method,path,body", ROUTES)
def test_service_without_auth_bridge_is_still_503(method, path, body):
    service, store = make()
    with TestClient(build(service=service, wire_service=True)) as client:
        assert call(client, method, path, body).status_code == 503
    assert not store.channels


@pytest.mark.parametrize("method,path,body", ROUTES)
def test_unauthenticated_is_401_and_writes_nothing(method, path, body):
    service, store = make()
    app = build(None, service, wire_actor=True, wire_service=True)
    with TestClient(app) as client:
        assert call(client, method, path, body).status_code == 401
    assert not store.channels and not store.requests and not store.claims


def test_no_approval_or_badge_routes_exist():
    paths = {route.path for route in router.routes}
    assert not any(
        word in path for path in paths for word in ("approve", "reject", "badge", "staff")
    )
    methods = {(m, route.path) for route in router.routes for m in route.methods}
    assert not any(m in {"PATCH", "PUT", "DELETE"} and "official" in p for m, p in methods)


def test_full_flow_create_join_edit_request_archive(wired):
    client, state, _ = wired
    body = {"department_id": str(DEPT), "name": "알고리즘 스터디", "description": "주 1회"}
    created = call(client, "post", "/free-channels", body)
    assert created.status_code == 201
    channel = created.json()["data"]["channel"]
    assert channel["is_official"] is False and channel["kind"] == "FREE"
    assert channel["my_role"] == "OWNER" and "owner_id" not in channel
    replay = call(client, "post", "/free-channels", body)
    assert replay.status_code == 200 and replay.json()["data"]["replayed"] is True
    cid = channel["id"]

    state["actor"] = BOB
    joined = call(client, "post", f"/free-channels/{cid}/join")
    assert joined.json()["data"]["changed"] is True
    assert joined.json()["data"]["channel"]["member_count"] == 2
    listed = call(client, "get", f"/departments/{DEPT}/free-channels?limit=1")
    assert listed.status_code == 200 and len(listed.json()["data"]["items"]) == 1
    forbidden = call(
        client, "patch", f"/free-channels/{cid}", {"name": "탈취", "expected_revision": 1}
    )
    assert forbidden.status_code == 403

    state["actor"] = ALICE
    edited = call(
        client, "patch", f"/free-channels/{cid}", {"name": "새 이름", "expected_revision": 1}
    )
    assert edited.status_code == 200 and edited.json()["resource_version"] == 2
    stale = call(client, "patch", f"/free-channels/{cid}", {"name": "또", "expected_revision": 1})
    assert stale.status_code == 409
    req = call(client, "post", f"/free-channels/{cid}/official-requests", {"reason": REASON})
    assert req.status_code == 201
    data = req.json()["data"]["request"]
    assert data["status"] == "PENDING" and data["review_state"] == "BLOCKED_APPROVER_POLICY"
    assert "requester_id" not in data
    archived = call(client, "post", f"/free-channels/{cid}/archive", {"expected_revision": 2})
    assert archived.json()["data"]["status"] == "ARCHIVED"
    mine = call(client, "get", f"/me/official-channel-requests/{data['id']}")
    assert mine.json()["data"]["status"] == "CANCELLED"

    state["actor"] = BOB
    assert call(client, "get", f"/me/official-channel-requests/{data['id']}").status_code == 404


def test_cross_department_and_default_channel(wired):
    client, state, _ = wired
    cid = call(client, "post", "/free-channels", {"department_id": str(DEPT), "name": "스터디"})
    cid = cid.json()["data"]["channel"]["id"]
    state["actor"] = DAVE
    assert call(client, "get", f"/free-channels/{cid}").status_code == 403
    assert call(client, "post", f"/free-channels/{cid}/join").status_code == 403
    assert call(client, "get", f"/departments/{DEPT}/free-channels").status_code == 403
    state["actor"] = ALICE
    edit = {"name": "x", "expected_revision": 1}
    assert call(client, "patch", f"/free-channels/{DEFAULT_CHANNEL}", edit).status_code == 403
    assert call(client, "post", f"/free-channels/{uuid4()}/join").status_code == 404


@pytest.mark.parametrize(
    "body",
    [
        {"department_id": str(DEPT), "name": "x", "owner_id": str(uuid4())},
        {"department_id": str(DEPT), "name": "x", "is_official": True},
        {"department_id": str(DEPT), "name": "x", "grade": 9},
        {"department_id": "not-a-uuid", "name": "x"},
        {"department_id": str(DEPT), "name": "secret‮value"},
        {"department_id": str(DEPT), "name": "y" * 200},
    ],
)
def test_create_validation_is_400_without_reflection(wired, body):
    client, _, store = wired
    response = call(client, "post", "/free-channels", body)
    assert response.status_code == 400
    assert "secret" not in response.text and "not-a-uuid" not in response.text
    assert not store.channels


@pytest.mark.parametrize("key", [None, "short", "has space 0000000000", "a" * 101])
def test_create_requires_valid_idempotency_key(wired, key):
    client, _, store = wired
    headers = {} if key is None else {"Idempotency-Key": key}
    response = client.post(
        "/api/v1/free-channels",
        json={"department_id": str(DEPT), "name": "x"},
        headers=headers,
    )
    assert response.status_code == 400 and not store.channels


@pytest.mark.parametrize("query", ["limit=0", "limit=51", "before=0", "limit=abc"])
def test_pagination_bounds(wired, query):
    client, _, _ = wired
    assert call(client, "get", f"/me/free-channels?{query}").status_code == 400


def test_non_uuid_ids_rejected(wired):
    client, _, _ = wired
    assert call(client, "get", "/free-channels/%EC%B1%84%EB%84%90").status_code == 400
    traversal = client.post("/api/v1/free-channels/..%2F..%2Fadmin/join", headers=HEADERS)
    assert traversal.status_code in {400, 404}
