"""HTTP contract tests for the API-OPP router (fail-closed defaults and injected providers)."""

from uuid import UUID, uuid4

import pytest
from fastapi import Header
from fastapi.testclient import TestClient
from test_opportunities_support import (
    USER_A,
    USER_B,
    FakeCatalog,
    FakeStore,
    make_opportunity,
)

from app.core.config import Settings
from app.core.errors import ApiError
from app.factory import create_app
from app.features.opportunities import OpportunityDependencies, Principal, create_router, router
from app.features.opportunities.router import parse_if_match
from app.features.opportunities.schemas import PublicationStatus
from app.schemas.common import ErrorCode

ERROR_KEYS = {"code", "message", "field_errors", "retryable", "request_id"}


def mount(feature_router):
    application = create_app(Settings(environment="test"))
    application.include_router(feature_router, prefix="/api/v1")
    return TestClient(application)


def fake_principal(x_test_user: str | None = Header(default=None)) -> Principal:
    """Test-only stand-in for the shared auth dependency."""
    if x_test_user is None:
        raise ApiError(ErrorCode.UNAUTHORIZED)
    return Principal(user_id=UUID(x_test_user))


@pytest.fixture
def env():
    published = make_opportunity()
    draft = make_opportunity(status=PublicationStatus.DRAFT)
    catalog, store = FakeCatalog([published, draft]), FakeStore()
    deps = OpportunityDependencies(
        current_principal=fake_principal, catalog=lambda: catalog, store=lambda: store
    )
    return dict(client=mount(create_router(deps)), store=store, oid=published.id, draft=draft.id)


def as_user(user: UUID, **extra) -> dict[str, str]:
    return {"X-Test-User": str(user), **extra}


@pytest.mark.parametrize(
    "method,path",
    [
        ("get", "/api/v1/opportunities"),
        ("get", f"/api/v1/opportunities/{uuid4()}"),
        ("get", "/api/v1/me/saved-opportunities"),
        ("put", f"/api/v1/me/saved-opportunities/{uuid4()}"),
    ],
)
def test_default_router_fails_closed_503(method, path):
    response = getattr(mount(router), method)(path)
    assert response.status_code == 503
    assert set(response.json()) == ERROR_KEYS
    assert response.json()["code"] == "UNAVAILABLE"


def test_unconfigured_auth_blocks_before_store_access():
    touched = []

    def store():
        touched.append(True)
        return FakeStore()

    deps = OpportunityDependencies(catalog=lambda: FakeCatalog([]), store=store)
    response = mount(create_router(deps)).get("/api/v1/me/saved-opportunities")
    assert response.status_code == 503 and touched == []


def test_public_list_and_detail(env):
    client = env["client"]
    listing = client.get("/api/v1/opportunities")
    assert listing.status_code == 200
    body = listing.json()
    assert set(body) == {"data", "resource_version", "server_time"}
    assert [i["id"] for i in body["data"]["items"]] == [str(env["oid"])]
    detail = client.get(f"/api/v1/opportunities/{env['oid']}").json()["data"]
    assert detail["submission_mode"] == "external_document_submission"
    assert detail["platform_receives_submission"] is False
    assert client.get(f"/api/v1/opportunities/{env['draft']}").status_code == 404


@pytest.mark.parametrize(
    "query", ["limit=0", "limit=51", "kind=unknown", "department=<script>", "q=" + "x" * 51]
)
def test_public_query_validation(env, query):
    response = env["client"].get(f"/api/v1/opportunities?{query}")
    assert response.status_code == 400 and response.json()["code"] == "VALIDATION"


def test_protected_requires_principal(env):
    response = env["client"].get("/api/v1/me/saved-opportunities")
    assert response.status_code == 401 and response.json()["code"] == "UNAUTHORIZED"


def test_owner_flow_over_http(env):
    client, oid = env["client"], env["oid"]
    base = f"/api/v1/me/saved-opportunities/{oid}"
    created = client.put(base, json={"memo": "추천서 요청"}, headers=as_user(USER_A))
    assert created.status_code == 201 and created.json()["resource_version"] == 1
    repeated = client.put(base, headers=as_user(USER_A))
    assert repeated.status_code == 200 and repeated.json()["data"]["memo"] == "추천서 요청"

    check = client.post(
        f"{base}/checks",
        json={"text": "지정 양식 작성", "sort_order": 0},
        headers=as_user(USER_A, **{"Idempotency-Key": "check-0001"}),
    )
    assert check.status_code == 201
    check_id = check.json()["data"]["id"]
    retry = client.post(
        f"{base}/checks",
        json={"text": "지정 양식 작성", "sort_order": 0},
        headers=as_user(USER_A, **{"Idempotency-Key": "check-0001"}),
    )
    assert retry.status_code == 200 and retry.json()["data"]["id"] == check_id

    toggled = client.patch(
        f"{base}/checks/{check_id}",
        json={"completed": True},
        headers=as_user(USER_A, **{"If-Match": '"1"'}),
    )
    assert toggled.status_code == 200 and toggled.json()["data"]["completed_at"]

    for revision, status in [(1, "preparing"), (2, "self_reported_submitted")]:
        moved = client.patch(
            base, json={"status": status}, headers=as_user(USER_A, **{"If-Match": str(revision)})
        )
        assert moved.status_code == 200, moved.text
    listing = client.get("/api/v1/me/saved-opportunities", headers=as_user(USER_A)).json()
    item = listing["data"]["items"][0]
    assert item["status"] == "self_reported_submitted"
    assert item["self_reported_submitted_at"] and item["checks"][0]["completed_at"]
    assert item["opportunity"]["id"] == str(oid)

    stale = client.delete(base, headers=as_user(USER_A, **{"If-Match": "1"}))
    assert stale.status_code == 409 and stale.json()["code"] == "CONFLICT"
    deleted = client.delete(base, headers=as_user(USER_A, **{"If-Match": "3"}))
    assert deleted.status_code == 200 and deleted.json()["data"] == {"deleted": True}
    assert env["store"].saved == {} and env["store"].checks == {}


def test_other_user_cannot_read_or_modify(env):
    client, oid = env["client"], env["oid"]
    base = f"/api/v1/me/saved-opportunities/{oid}"
    client.put(base, json={"memo": "A의 비공개 메모"}, headers=as_user(USER_A))
    listing = client.get("/api/v1/me/saved-opportunities", headers=as_user(USER_B))
    assert listing.json()["data"]["items"] == []
    assert "A의 비공개 메모" not in listing.text
    for method, kwargs in [
        ("patch", {"json": {"memo": "x"}}),
        ("delete", {}),
    ]:
        response = getattr(client, method)(
            base, headers=as_user(USER_B, **{"If-Match": "1"}), **kwargs
        )
        assert response.status_code == 404
        assert "A의 비공개 메모" not in response.text
    assert next(iter(env["store"].saved.values())).memo == "A의 비공개 메모"


def test_body_identity_is_ignored_and_rejected(env):
    response = env["client"].put(
        f"/api/v1/me/saved-opportunities/{env['oid']}",
        json={"memo": "x", "user_id": str(USER_B)},
        headers=as_user(USER_A),
    )
    assert response.status_code == 400 and response.json()["code"] == "VALIDATION"
    assert env["store"].saved == {}


@pytest.mark.parametrize(
    "if_match",
    [
        None,
        "abc",
        "0",
        "-1",
        "1" * 12,
        "1234567890",
        "01",
        'W/"1"',
        'w/"1"',
        '""1',
        '1""',
        '"1',
        '1"',
        '""1""',
        '"1", "2"',
        "1, 2",
        "*",
        '"*"',
        '" 1"',
        "+1",
        "",
    ],
)
def test_if_match_required_and_validated(env, if_match):
    client, oid = env["client"], env["oid"]
    client.put(f"/api/v1/me/saved-opportunities/{oid}", headers=as_user(USER_A))
    headers = as_user(USER_A) if if_match is None else as_user(USER_A, **{"If-Match": if_match})
    response = client.patch(
        f"/api/v1/me/saved-opportunities/{oid}", json={"memo": "x"}, headers=headers
    )
    assert response.status_code == 400 and response.json()["code"] == "VALIDATION"


@pytest.mark.parametrize("key", [None, "short", "has space key", "x" * 101])
def test_idempotency_key_required(env, key):
    client, oid = env["client"], env["oid"]
    client.put(f"/api/v1/me/saved-opportunities/{oid}", headers=as_user(USER_A))
    headers = as_user(USER_A) if key is None else as_user(USER_A, **{"Idempotency-Key": key})
    response = client.post(
        f"/api/v1/me/saved-opportunities/{oid}/checks",
        json={"text": "a", "sort_order": 0},
        headers=headers,
    )
    assert response.status_code == 400


def test_invalid_status_transition_is_conflict(env):
    client, oid = env["client"], env["oid"]
    client.put(f"/api/v1/me/saved-opportunities/{oid}", headers=as_user(USER_A))
    response = client.patch(
        f"/api/v1/me/saved-opportunities/{oid}",
        json={"status": "self_reported_submitted"},
        headers=as_user(USER_A, **{"If-Match": "1"}),
    )
    assert response.status_code == 409


def test_save_draft_is_not_found(env):
    response = env["client"].put(
        f"/api/v1/me/saved-opportunities/{env['draft']}", headers=as_user(USER_A)
    )
    assert response.status_code == 404 and env["store"].saved == {}


def test_feature_openapi_has_no_identity_inputs(env):
    schema = env["client"].app.openapi()
    paths = [p for p in schema["paths"] if "opportunities" in p]
    assert "/api/v1/me/saved-opportunities/{opportunity_id}/checks/{check_id}" in paths
    for path in paths:
        for operation in schema["paths"][path].values():
            names = {p["name"].lower() for p in operation.get("parameters", [])}
            assert names.isdisjoint({"user_id", "role", "department_id", "academic_year"})


@pytest.mark.parametrize(
    "value,expected", [("1", 1), ('"1"', 1), (" 7\t", 7), ('"999999999"', 999999999)]
)
def test_parse_if_match_accepts_bare_or_strong_tag(value, expected):
    assert parse_if_match(value) == expected


@pytest.mark.parametrize("value", ["١", "１", '"١"', "1٢", "²"])
def test_parse_if_match_rejects_non_ascii_digits(value):
    with pytest.raises(ApiError) as exc:
        parse_if_match(value)
    assert exc.value.code == ErrorCode.VALIDATION


@pytest.mark.parametrize("if_match", ["1", '"1"'])
def test_if_match_strong_tag_reaches_service(env, if_match):
    client, oid = env["client"], env["oid"]
    client.put(f"/api/v1/me/saved-opportunities/{oid}", headers=as_user(USER_A))
    response = client.patch(
        f"/api/v1/me/saved-opportunities/{oid}",
        json={"memo": "x"},
        headers=as_user(USER_A, **{"If-Match": if_match}),
    )
    assert response.status_code == 200 and response.json()["resource_version"] == 2


def test_check_replay_after_delete_is_conflict_not_new_item(env):
    client, store, oid = env["client"], env["store"], env["oid"]
    client.put(f"/api/v1/me/saved-opportunities/{oid}", headers=as_user(USER_A))
    url = f"/api/v1/me/saved-opportunities/{oid}/checks"
    headers = as_user(USER_A, **{"Idempotency-Key": "check-replay"})
    body = {"text": "추천서", "sort_order": 0}
    created = client.post(url, json=body, headers=headers)
    assert created.status_code == 201
    check_id = created.json()["data"]["id"]
    deleted = client.delete(f"{url}/{check_id}", headers=as_user(USER_A, **{"If-Match": "1"}))
    assert deleted.status_code == 200
    replay = client.post(url, json=body, headers=headers)
    assert replay.status_code == 409 and replay.json()["code"] == "CONFLICT"
    assert store.checks == {}


def test_status_event_failure_returns_500_and_keeps_state():
    published = make_opportunity()
    catalog, store = FakeCatalog([published]), FakeStore(fail_event_append=True)
    deps = OpportunityDependencies(
        current_principal=fake_principal, catalog=lambda: catalog, store=lambda: store
    )
    application = create_app(Settings(environment="test"))
    application.include_router(create_router(deps), prefix="/api/v1")
    client = TestClient(application, raise_server_exceptions=False)
    base = f"/api/v1/me/saved-opportunities/{published.id}"
    client.put(base, headers=as_user(USER_A))
    response = client.patch(
        base, json={"status": "preparing"}, headers=as_user(USER_A, **{"If-Match": "1"})
    )
    assert response.status_code == 500 and set(response.json()) == ERROR_KEYS
    row = store.get(USER_A, published.id)
    assert row.status == "interested" and row.revision == 1 and store.events == []
