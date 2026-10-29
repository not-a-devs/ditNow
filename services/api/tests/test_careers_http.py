"""HTTP contract for the API-JOB router: fail-closed defaults, authz order, cache, replay."""

from datetime import timedelta
from uuid import UUID, uuid4

import pytest
from fastapi import Header
from fastapi.testclient import TestClient
from test_careers_support import (
    ALL_STUDENT,
    NOW,
    USER_A,
    USER_B,
    FakeTransaction,
    FakeUnitOfWork,
    demo_policy,
    make_program,
)
from test_opportunities_support import FakeCatalog, make_opportunity

from app.core.config import Settings
from app.core.errors import ApiError
from app.factory import create_app
from app.features.careers import (
    CareerGrant,
    CareersActor,
    CareersDependencies,
    create_careers_router,
    router,
)
from app.features.careers.ports import StoreBusy
from app.features.careers.router import parse_if_match
from app.features.careers.service import MAX_TX_ATTEMPTS
from app.features.opportunities.schemas import OpportunityKind

PRIVATE = "private, no-store"
ERROR_KEYS = {"code", "message", "field_errors", "retryable", "request_id"}
DRAFTER = UUID("00000000-0000-4000-8000-0000000000d1")


def mount(feature_router) -> TestClient:
    application = create_app(Settings(environment="test"))
    application.include_router(feature_router, prefix="/api/v1")
    return TestClient(application)


def fake_actor(x_test_user: str | None = Header(default=None)) -> CareersActor | None:
    """Test-only stand-in for the shared verified session. Never used outside tests."""
    return CareersActor(user_id=UUID(x_test_user)) if x_test_user else None


def as_user(user: UUID, **headers) -> dict[str, str]:
    return {"X-Test-User": str(user), **headers}


@pytest.fixture
def env():
    program = make_program()
    uow = FakeUnitOfWork([program])
    uow.grant(USER_A, *ALL_STUDENT)
    uow.grant(USER_B, *ALL_STUDENT)
    uow.grant(DRAFTER, CareerGrant.EMPLOYER_DRAFT)
    career = make_opportunity(kind=OpportunityKind.CAREER, title="[DEMO] 가상 인턴")
    contest = make_opportunity(kind=OpportunityKind.CONTEST, title="[DEMO] 가상 공모전")
    deps = CareersDependencies(
        actor=fake_actor,
        catalog=lambda: FakeCatalog([career, contest]),
        uow=lambda: uow,
        policy=lambda: demo_policy(),
        clock=lambda: NOW,
    )
    return dict(
        client=mount(create_careers_router(deps)),
        uow=uow,
        program=program,
        career=career,
        contest=contest,
    )


ALL_ROUTES = [
    ("get", "/api/v1/careers/jobs"),
    ("get", f"/api/v1/careers/jobs/{uuid4()}"),
    ("get", "/api/v1/careers/contests"),
    ("get", "/api/v1/careers/me/profile"),
    ("post", "/api/v1/careers/me/profile"),
    ("patch", "/api/v1/careers/me/profile"),
    ("delete", "/api/v1/careers/me/profile"),
    ("get", "/api/v1/careers/programs"),
    ("post", f"/api/v1/careers/programs/{uuid4()}/applications"),
    ("get", "/api/v1/careers/me/program-applications"),
    ("get", f"/api/v1/careers/me/program-applications/{uuid4()}"),
    ("post", f"/api/v1/careers/me/program-applications/{uuid4()}/cancel"),
    ("get", "/api/v1/careers/employer-requests"),
    ("post", "/api/v1/careers/employer-requests"),
    ("get", f"/api/v1/careers/employer-requests/{uuid4()}"),
    ("patch", f"/api/v1/careers/employer-requests/{uuid4()}"),
    ("delete", f"/api/v1/careers/employer-requests/{uuid4()}"),
]


@pytest.mark.parametrize("method,path", ALL_ROUTES)
def test_default_router_fails_closed_with_private_cache(method, path):
    response = getattr(mount(router), method)(path, headers=as_user(USER_A))
    assert response.status_code == 503
    assert set(response.json()) == ERROR_KEYS and response.json()["code"] == "UNAVAILABLE"
    assert response.headers["Cache-Control"] == PRIVATE


def test_global_app_does_not_mount_careers():
    application = create_app(Settings(environment="test"))
    assert TestClient(application).get("/api/v1/careers/jobs").status_code == 404
    assert not any("/careers" in p for p in application.openapi().get("paths", {}))


@pytest.mark.parametrize(
    "method,path",
    [(m, p) for m, p in ALL_ROUTES if "/me/" in p or "employer" in p or m != "get"],
)
def test_anonymous_gets_401_before_any_transaction(env, method, path):
    response = getattr(env["client"], method)(path)
    assert response.status_code == 401 and response.json()["code"] == "UNAUTHORIZED"
    assert response.headers["Cache-Control"] == PRIVATE
    assert env["uow"].transactions == 0


def test_forbidden_precedes_body_and_header_validation(env):
    # Student without the employer-draft grant sends an invalid body and no Idempotency-Key.
    response = env["client"].post(
        "/api/v1/careers/employer-requests", json={"user_id": "x"}, headers=as_user(USER_A)
    )
    assert response.status_code == 403 and response.json()["code"] == "FORBIDDEN"
    assert response.headers["Cache-Control"] == PRIVATE
    assert env["uow"].drafts == {}


def test_public_jobs_and_contests_use_catalog(env):
    client = env["client"]
    jobs = client.get("/api/v1/careers/jobs")
    assert jobs.status_code == 200 and jobs.headers["Cache-Control"] == PRIVATE
    assert [item["id"] for item in jobs.json()["data"]["items"]] == [str(env["career"].id)]
    assert jobs.json()["data"]["items"][0]["provenance"] == "DEMO"
    assert client.get(f"/api/v1/careers/jobs/{env['contest'].id}").status_code == 404
    contests = client.get("/api/v1/careers/contests").json()["data"]["items"]
    assert contests[0]["opportunity_id"] == str(env["contest"].id)
    assert contests[0]["team_link_candidate"] is True
    assert contests[0]["reference_field"] == "opportunity_id"
    assert client.get("/api/v1/careers/jobs?limit=0").status_code == 400


def test_profile_create_replay_and_conflicts_over_http(env):
    client, body = env["client"], {"alias": "별빛개발자", "skills": ["Python"]}
    headers = as_user(USER_A, **{"Idempotency-Key": "profile-key-001"})
    first = client.post("/api/v1/careers/me/profile", json=body, headers=headers)
    assert first.status_code == 201 and first.json()["resource_version"] == 1
    assert first.headers["Cache-Control"] == PRIVATE
    replay = client.post("/api/v1/careers/me/profile", json=body, headers=headers)
    assert replay.status_code == 200 and replay.headers["Idempotent-Replayed"] == "true"
    assert replay.json()["data"]["id"] == first.json()["data"]["id"]
    changed = client.post(
        "/api/v1/careers/me/profile", json={**body, "alias": "다른별칭"}, headers=headers
    )
    assert changed.status_code == 409

    other = client.get("/api/v1/careers/me/profile", headers=as_user(USER_B))
    assert other.status_code == 200 and other.json()["data"] == {"profile": None}
    mine = client.get("/api/v1/careers/me/profile", headers=as_user(USER_A)).json()
    assert mine["data"]["profile"]["alias"] == "별빛개발자" and mine["resource_version"] == 1


@pytest.mark.parametrize(
    "body",
    [
        {"alias": "별빛", "user_id": str(USER_B)},
        {"alias": "별빛", "email": "a@b.kr"},
        {"alias": "별빛", "resume_file": "cv.pdf"},
        {"alias": "a@b.kr"},
        {"alias": "별빛", "summary": "연락 010 1234 5678"},
    ],
)
def test_profile_rejects_identity_contact_and_file_fields(env, body):
    response = env["client"].post(
        "/api/v1/careers/me/profile",
        json=body,
        headers=as_user(USER_A, **{"Idempotency-Key": "profile-key-001"}),
    )
    assert response.status_code == 400 and response.json()["code"] == "VALIDATION"
    assert "010" not in response.text and "a@b.kr" not in response.text  # no input echo
    assert response.headers["Cache-Control"] == PRIVATE
    assert env["uow"].profiles == {}


@pytest.mark.parametrize("value", ['W/"1"', "*", "1, 2", "01", '"1', "abc", "0"])
def test_if_match_must_be_one_strong_revision(env, value):
    env["client"].post(
        "/api/v1/careers/me/profile",
        json={"alias": "별빛개발자"},
        headers=as_user(USER_A, **{"Idempotency-Key": "profile-key-001"}),
    )
    response = env["client"].patch(
        "/api/v1/careers/me/profile",
        json={"summary": "x"},
        headers=as_user(USER_A, **{"If-Match": value}),
    )
    assert response.status_code == 400


def test_parse_if_match_accepts_bare_and_quoted():
    assert parse_if_match("3") == parse_if_match('"3"') == 3
    with pytest.raises(ApiError):
        parse_if_match("１")  # non-ASCII digit (httpx cannot send it, so checked directly)


def test_missing_or_bad_idempotency_key_is_400(env):
    path = f"/api/v1/careers/programs/{env['program'].id}/applications"
    for headers in (as_user(USER_A), as_user(USER_A, **{"Idempotency-Key": "short"})):
        response = env["client"].post(path, json={}, headers=headers)
        assert response.status_code == 400
    assert env["uow"].applications == {}


def test_program_application_flow_and_cross_account_404(env):
    client, program = env["client"], env["program"]
    path = f"/api/v1/careers/programs/{program.id}/applications"
    headers = as_user(USER_A, **{"Idempotency-Key": "apply-key-0001"})
    created = client.post(path, json={"note": "참여 희망"}, headers=headers)
    assert created.status_code == 201
    app_id = created.json()["data"]["id"]
    assert created.json()["data"]["review_status"] == "not_reviewed"
    assert client.post(path, json={"note": "참여 희망"}, headers=headers).status_code == 200

    item = f"/api/v1/careers/me/program-applications/{app_id}"
    assert client.get(item, headers=as_user(USER_B)).status_code == 404
    other_cancel = client.post(f"{item}/cancel", headers=as_user(USER_B, **{"If-Match": "1"}))
    assert other_cancel.status_code == 404
    assert client.get(item, headers=as_user(USER_A)).status_code == 200
    stale = client.post(f"{item}/cancel", headers=as_user(USER_A, **{"If-Match": "9"}))
    assert stale.status_code == 409
    cancelled = client.post(f"{item}/cancel", headers=as_user(USER_A, **{"If-Match": "1"}))
    assert cancelled.status_code == 200 and cancelled.json()["data"]["status"] == "cancelled"

    listing = client.get("/api/v1/careers/programs").json()["data"]
    assert listing["policy_basis"] == "DEMO" and listing["policy_id"] == "demo-careers-20261030"


def test_revoked_grant_blocks_replay_over_http(env):
    client, program = env["client"], env["program"]
    path = f"/api/v1/careers/programs/{program.id}/applications"
    headers = as_user(USER_A, **{"Idempotency-Key": "apply-key-0001"})
    assert client.post(path, json={}, headers=headers).status_code == 201
    env["uow"].grant(USER_A, CareerGrant.PROFILE_SELF)
    replay = client.post(path, json={}, headers=headers)
    assert replay.status_code == 403 and "Idempotent-Replayed" not in replay.headers


def test_employer_draft_flow_and_tombstone_over_http(env):
    client = env["client"]
    body = {
        "company_alias": "가상테크",
        "role_title": "[DEMO] 백엔드 인턴",
        "description": "가상 초안",
        "employment_type": "internship",
        "closes_at": (NOW + timedelta(days=10)).isoformat(),
    }
    headers = as_user(DRAFTER, **{"Idempotency-Key": "draft-key-0001"})
    created = client.post("/api/v1/careers/employer-requests", json=body, headers=headers)
    assert created.status_code == 201 and created.json()["data"]["publishable"] is False
    draft_id = created.json()["data"]["id"]
    item = f"/api/v1/careers/employer-requests/{draft_id}"
    assert client.get(item, headers=as_user(USER_A)).status_code == 403  # student: no grant
    naive = client.post(
        "/api/v1/careers/employer-requests",
        json={**body, "closes_at": "2026-12-01T00:00:00"},
        headers=as_user(DRAFTER, **{"Idempotency-Key": "draft-key-0002"}),
    )
    assert naive.status_code == 400
    deleted = client.delete(item, headers=as_user(DRAFTER, **{"If-Match": "1"}))
    assert deleted.status_code == 200 and deleted.json()["data"]["deleted"] is True
    late = client.post("/api/v1/careers/employer-requests", json=body, headers=headers)
    assert late.status_code == 409
    assert client.get(item, headers=as_user(DRAFTER)).status_code == 404


def test_deadlock_or_lock_timeout_is_bounded_409_without_driver_text(env, monkeypatch):
    def busy(self, user_id):
        raise StoreBusy("Deadlock found when trying to get lock (1213) password=secret")

    monkeypatch.setattr(FakeTransaction, "lock_actor", busy)
    client, program, uow = env["client"], env["program"], env["uow"]
    before = uow.transactions
    response = client.post(
        f"/api/v1/careers/programs/{program.id}/applications",
        json={},
        headers=as_user(USER_A, **{"Idempotency-Key": "apply-key-busy"}),
    )
    assert response.status_code == 409 and set(response.json()) == ERROR_KEYS
    for leaked in ("1213", "Deadlock", "secret"):
        assert leaked not in response.text
    assert response.headers["Cache-Control"] == PRIVATE
    # 1 route grant check + MAX_TX_ATTEMPTS service transactions, nothing written.
    assert uow.transactions - before == 1 + MAX_TX_ATTEMPTS
    assert uow.applications == {} and uow.claims == {}


def test_unexpected_store_error_is_500_without_leak_and_private(env):
    class Broken:
        def transaction(self):
            raise RuntimeError("db password=secret")

    deps = CareersDependencies(actor=fake_actor, uow=lambda: Broken(), policy=lambda: demo_policy())
    client = TestClient(mount(create_careers_router(deps)).app, raise_server_exceptions=False)
    response = client.get("/api/v1/careers/me/profile", headers=as_user(USER_A))
    assert response.status_code == 500 and "secret" not in response.text
    assert response.headers["Cache-Control"] == PRIVATE
