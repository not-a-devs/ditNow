"""HTTP contract and fail-closed checks for the campus router (not mounted in the real app)."""

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from test_campus_support import DEPT_A, DEPT_B, World, assistant, student

from app.core.config import Settings
from app.factory import create_app
from app.features.campus import CampusRuntime, build_campus_router, router

PREFIX = "/api/v1"


class HeaderActorResolver:
    """Test-only: maps an opaque header to a pre-built actor. Not an auth implementation."""

    def __init__(self, actors) -> None:
        self.actors = actors

    def resolve(self, request):
        return self.actors.get(request.headers.get("X-Test-Actor", ""))


def make_client(campus_router) -> TestClient:
    application = create_app(Settings(environment="test"))
    application.include_router(campus_router, prefix=PREFIX)
    return TestClient(application)


@pytest.fixture
def setup():
    world = World()
    actors = {
        "a2": student(DEPT_A, 2),
        "a2b": student(DEPT_A, 2),
        "a1": student(DEPT_A, 1),
        "b2": student(DEPT_B, 2),
        "ta": assistant(DEPT_A, 2),
    }
    runtime = CampusRuntime(
        HeaderActorResolver(actors),
        world.channels,
        world.messages,
        world.notices,
        world.calendar,
        world.clock,
    )
    with make_client(build_campus_router(lambda: runtime)) as client:
        yield client, world, actors


def as_(actor: str) -> dict[str, str]:
    return {"X-Test-Actor": actor}


PROTECTED = [
    ("GET", f"/departments/{DEPT_A}/channels", None),
    ("GET", f"/channels/{uuid4()}/messages", None),
    ("POST", f"/channels/{uuid4()}/messages", {"body": "x", "client_nonce": "nonce-0000-1"}),
    ("GET", "/notices", None),
    (
        "POST",
        "/notices",
        {"audience": {"type": "SCHOOL"}, "title": "t", "body": "b"},
    ),
    ("GET", f"/notices/{uuid4()}", None),
    ("PATCH", f"/notices/{uuid4()}", {"title": "t", "body": "b", "expected_revision": 1}),
    ("POST", f"/notices/{uuid4()}/publish", None),
    ("POST", f"/notices/{uuid4()}/archive", None),
    ("GET", "/academic/terms", None),
    ("GET", f"/academic/terms/{uuid4()}/events", None),
]


@pytest.mark.parametrize(("method", "path", "body"), PROTECTED)
def test_default_router_fails_closed_with_503(method, path, body):
    with make_client(router) as client:
        response = client.request(method, PREFIX + path, json=body)
    assert response.status_code == 503
    payload = response.json()
    assert payload["code"] == "UNAVAILABLE" and payload["retryable"] is True
    assert payload["request_id"] == response.headers["X-Request-ID"]


@pytest.mark.parametrize(("method", "path", "body"), PROTECTED)
def test_unauthenticated_requests_get_401_before_anything(setup, method, path, body):
    client, world, _ = setup
    response = client.request(method, PREFIX + path, json=body, headers=as_("forged"))
    assert response.status_code == 401
    assert response.json()["code"] == "UNAUTHORIZED"
    assert world.messages.rows == [] and world.notices.rows == {}


def test_chat_roundtrip_and_isolation(setup):
    client, world, _ = setup
    url = f"{PREFIX}/channels/{world.a_2.id}/messages"
    sent = client.post(
        url, json={"body": "안녕", "client_nonce": "nonce-http-01"}, headers=as_("a2")
    )
    assert sent.status_code == 201
    assert sent.json()["data"]["replayed"] is False
    replay = client.post(
        url, json={"body": "안녕", "client_nonce": "nonce-http-01"}, headers=as_("a2")
    )
    assert replay.status_code == 200 and replay.json()["data"]["replayed"] is True
    listed = client.get(url, headers=as_("a2b")).json()["data"]["items"]
    assert [(m["body"], m["is_mine"]) for m in listed] == [("안녕", False)]
    for outsider in ("a1", "b2"):
        assert client.get(url, headers=as_(outsider)).status_code == 403
    channels = client.get(f"{PREFIX}/departments/{DEPT_A}/channels", headers=as_("a2")).json()
    assert {c["id"] for c in channels["data"]["items"]} == {str(world.a_all.id), str(world.a_2.id)}
    assert client.get(f"{PREFIX}/departments/{DEPT_A}/channels", headers=as_("b2")).status_code == (
        403
    )


@pytest.mark.parametrize(
    "body",
    [
        {"body": "", "client_nonce": "nonce-http-02"},
        {"body": "x", "client_nonce": "bad"},
        {"body": "x", "client_nonce": "nonce-http-02", "author_id": str(uuid4())},
        {"body": "x" * 2001, "client_nonce": "nonce-http-02"},
    ],
)
def test_message_validation_returns_400_without_echo(setup, body):
    client, world, _ = setup
    response = client.post(
        f"{PREFIX}/channels/{world.a_2.id}/messages", json=body, headers=as_("a2")
    )
    assert response.status_code == 400
    assert response.json()["code"] == "VALIDATION"
    assert "nonce-http-02" not in response.text
    assert world.messages.rows == []


def test_notice_flow_over_http(setup):
    client, world, _ = setup
    audience = {"type": "DEPARTMENT_GRADE", "department_id": str(DEPT_A), "grade": 2}
    created = client.post(
        f"{PREFIX}/notices",
        json={"audience": audience, "title": "가상 공지", "body": "본문"},
        headers=as_("ta"),
    )
    assert created.status_code == 201
    notice_id = created.json()["data"]["id"]
    assert created.json()["resource_version"] == 1
    assert client.get(f"{PREFIX}/notices/{notice_id}", headers=as_("a2")).status_code == 404
    for _ in range(3):
        published = client.post(f"{PREFIX}/notices/{notice_id}/publish", headers=as_("ta"))
        assert published.status_code == 200
    assert published.json()["data"]["delivery"]["created_count"] == 0
    revised = client.patch(
        f"{PREFIX}/notices/{notice_id}",
        json={"title": "가상 공지 v2", "body": "수정", "expected_revision": 1},
        headers=as_("ta"),
    )
    assert revised.json()["resource_version"] == 2
    stale = client.patch(
        f"{PREFIX}/notices/{notice_id}",
        json={"title": "x", "body": "y", "expected_revision": 1},
        headers=as_("ta"),
    )
    assert stale.status_code == 409
    items = client.get(f"{PREFIX}/channels/{world.a_2.id}/messages", headers=as_("a2")).json()
    cards = [m for m in items["data"]["items"] if m["kind"] == "NOTICE_CARD"]
    assert len(cards) == 1 and cards[0]["notice"]["title"] == "가상 공지 v2"
    view = client.get(f"{PREFIX}/notices/{notice_id}", headers=as_("a2")).json()["data"]
    assert view["revision"] == 2 and view["can_manage"] is False
    assert client.get(f"{PREFIX}/notices/{notice_id}", headers=as_("b2")).status_code == 403
    assert client.post(f"{PREFIX}/notices/{notice_id}/archive", headers=as_("a2")).status_code == (
        403
    )


def test_student_cannot_create_official_notice(setup):
    client, world, _ = setup
    response = client.post(
        f"{PREFIX}/notices",
        json={
            "audience": {"type": "DEPARTMENT_GRADE", "department_id": str(DEPT_A), "grade": 2},
            "title": "가짜 공지",
            "body": "b",
        },
        headers=as_("a2"),
    )
    assert response.status_code == 403
    assert world.notices.rows == {}


@pytest.mark.parametrize(
    "audience",
    [
        {"type": "SCHOOL", "department_id": str(DEPT_A)},
        {"type": "DEPARTMENT_GRADE", "department_id": str(DEPT_A)},
        {"type": "DEPARTMENT_GRADE", "department_id": str(DEPT_A), "grade": 9},
        {"type": "CLASS"},
    ],
)
def test_malformed_audience_is_400(setup, audience):
    client, _, _ = setup
    response = client.post(
        f"{PREFIX}/notices",
        json={"audience": audience, "title": "t", "body": "b"},
        headers=as_("ta"),
    )
    assert response.status_code == 400


def test_academic_calendar_over_http(setup):
    client, world, _ = setup
    terms = client.get(f"{PREFIX}/academic/terms", headers=as_("a2")).json()["data"]["items"]
    assert terms[0]["id"] == str(world.term.id) and terms[0]["source_kind"] == "DEMO"
    events = client.get(
        f"{PREFIX}/academic/terms/{world.term.id}/events",
        params={"from": "2026-10-01", "to": "2026-10-31"},
        headers=as_("a2"),
    ).json()["data"]
    assert [e["title"] for e in events["items"]] == ["가상 중간고사"]
    bad = client.get(
        f"{PREFIX}/academic/terms/{world.term.id}/events",
        params={"from": "2026-11-01", "to": "2026-10-01"},
        headers=as_("a2"),
    )
    assert bad.status_code == 400


def test_mounted_router_produces_typed_openapi():
    application = create_app(Settings(environment="test"))
    application.include_router(router, prefix=PREFIX)
    schema = application.openapi()
    send = schema["paths"][f"{PREFIX}/channels/{{channel_id}}/messages"]["post"]
    assert set(send["responses"]) >= {"201", "401", "403", "404", "409", "503"}
    components = schema["components"]["schemas"]
    assert {"MessageCreate", "NoticeCreate", "AudienceModel"} <= set(components)
    assert "author_id" not in components["MessageCreate"]["properties"]


def test_router_is_not_mounted_in_shared_app():
    schema = create_app(Settings(environment="test")).openapi()
    assert not any(path.startswith(f"{PREFIX}/notices") for path in schema["paths"])
