"""Router contract for the unmounted academics module (test-only dependency overrides).

TC-V1-ACA-003~009 / TC-V1-ATT-001~002 HTTP layer: fail-closed 503, private no-store, input
validation, rule codes, 404 non-disclosure and redaction. Not a global-app/E2E/DB result.
"""

import logging
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from test_academics_support import (
    CODE,
    OFFERING_A,
    OFFERING_FULL,
    OTHER,
    STUDENT,
    TEACHER,
    TERM,
    make_service,
    seeded_store,
)

from app.core.config import Settings
from app.factory import create_app
from app.features.academics.router import get_academics_actor, get_academics_service, router

KEY = {"Idempotency-Key": "key-0000000000000001"}
BASE = "/api/v1/academics"


def build(actor=STUDENT, service=None):
    app = create_app(Settings(environment="test"))
    app.include_router(router, prefix="/api/v1")
    if actor is not None:
        app.dependency_overrides[get_academics_actor] = lambda: actor
    if service is not None:
        app.dependency_overrides[get_academics_service] = lambda: service
    return app


@pytest.fixture
def wired():
    store = seeded_store()
    service = make_service(store)
    state = {"actor": STUDENT}
    app = build(None, service)
    app.dependency_overrides[get_academics_actor] = lambda: state["actor"]
    with TestClient(app) as client:
        yield client, state, store


def private(response):
    assert response.headers["Cache-Control"] == "private, no-store"
    return response


def test_global_app_does_not_mount_academics():
    with TestClient(create_app(Settings(environment="test"))) as client:
        assert client.get(f"{BASE}/offerings").status_code == 404
    assert not any(
        "/academics" in path for path in create_app(Settings(environment="test")).openapi()["paths"]
    )


@pytest.mark.parametrize(
    "method,path",
    [
        ("get", "/policy"),
        ("get", "/offerings"),
        ("get", "/enrollments"),
        ("get", "/records"),
        ("get", "/requests"),
        ("get", f"/attendance/offerings/{OFFERING_A}/me"),
    ],
)
def test_unconfigured_auth_or_store_fails_closed(method, path):
    for app in (build(actor=None), build(actor=STUDENT)):
        with TestClient(app) as client:
            response = private(getattr(client, method)(BASE + path))
        assert response.status_code == 503 and response.json()["code"] == "UNAVAILABLE"


def test_unconfigured_policy_is_503_and_private():
    app = build(STUDENT, make_service(seeded_store(), policy=None))
    with TestClient(app) as client:
        response = private(
            client.post(f"{BASE}/enrollments", json={"offering_id": str(OFFERING_A)}, headers=KEY)
        )
        assert response.status_code == 503
        assert private(client.get(f"{BASE}/offerings")).status_code == 200


def test_enrollment_http_flow_and_rule_codes(wired):
    client, state, store = wired
    body = {"offering_id": str(OFFERING_A)}
    assert private(client.post(f"{BASE}/enrollments", json=body)).status_code == 400
    bad_key = {"Idempotency-Key": "short"}
    assert client.post(f"{BASE}/enrollments", json=body, headers=bad_key).status_code == 400
    forged = client.post(
        f"{BASE}/enrollments", json=body | {"student_id": str(OTHER.user_id)}, headers=KEY
    )
    assert forged.status_code == 400
    created = private(client.post(f"{BASE}/enrollments", json=body, headers=KEY))
    assert created.status_code == 200
    data = created.json()["data"]
    assert data["status"] == "ENROLLED" and "student_id" not in data
    assert str(STUDENT.user_id) not in created.text
    replay = client.post(f"{BASE}/enrollments", json=body, headers=KEY)
    assert replay.json()["data"]["id"] == data["id"]
    full = private(
        client.post(
            f"{BASE}/enrollments",
            json={"offering_id": str(OFFERING_FULL)},
            headers={"Idempotency-Key": "key-0000000000000002"},
        )
    )
    assert full.status_code == 409 and full.json()["field_errors"] == {"rule": "CAPACITY_FULL"}
    stale = client.post(f"{BASE}/enrollments/{data['id']}/drop", json={"expected_revision": 9})
    assert stale.status_code == 409 and stale.json()["field_errors"]["rule"] == "STALE_REVISION"
    state["actor"] = OTHER
    hidden = private(
        client.post(f"{BASE}/enrollments/{data['id']}/drop", json={"expected_revision": 1})
    )
    missing = client.post(f"{BASE}/enrollments/{uuid4()}/drop", json={"expected_revision": 1})
    assert hidden.status_code == missing.status_code == 404
    assert hidden.json()["message"] == missing.json()["message"]
    assert client.get(f"{BASE}/enrollments").json()["data"] == []


def test_catalog_query_validation(wired):
    client, _, _ = wired
    assert client.get(f"{BASE}/offerings?limit=101").status_code == 400
    assert client.get(f"{BASE}/offerings?q=" + "x" * 81).status_code == 400
    listing = private(client.get(f"{BASE}/offerings?term_id={TERM}&q=자료"))
    assert [o["title"] for o in listing.json()["data"]] == ["가상 자료구조"]
    assert client.get(f"{BASE}/offerings/not-a-uuid").status_code == 400


def test_request_http_flow_and_non_disclosure(wired):
    client, state, _ = wired
    body = {"kind": "READMISSION", "target_term_id": str(TERM), "reason": "가상 사유"}
    assert (
        client.post(
            f"{BASE}/requests", json=body | {"status": "SUBMITTED"}, headers=KEY
        ).status_code
        == 400
    )
    assert (
        client.post(f"{BASE}/requests", json=body | {"attachment": "x"}, headers=KEY).status_code
        == 400
    )
    created = private(client.post(f"{BASE}/requests", json=body, headers=KEY)).json()["data"]
    assert created["review_state"] == "NOT_CONNECTED" and created["official_effect"] == "NONE"
    changed = client.post(f"{BASE}/requests", json=body | {"reason": "다른"}, headers=KEY)
    assert changed.status_code == 409
    state["actor"] = OTHER
    assert (
        client.post(
            f"{BASE}/requests/{created['id']}/submit", json={"expected_revision": 1}
        ).status_code
        == 404
    )
    state["actor"] = STUDENT
    submitted = client.post(
        f"{BASE}/requests/{created['id']}/submit", json={"expected_revision": 1}
    )
    assert submitted.json()["data"]["status"] == "SUBMITTED"
    withdrawn = client.post(
        f"{BASE}/requests/{created['id']}/withdraw", json={"expected_revision": 2}
    )
    assert withdrawn.json()["data"] == withdrawn.json()["data"] | {
        "status": "WITHDRAWN",
        "reason": None,
    }


def test_attendance_http_roles_code_and_bluetooth_blocked(wired):
    client, state, _ = wired
    path = f"{BASE}/attendance/offerings/{OFFERING_A}"
    assert client.post(f"{path}/sessions", json={"label": "1주"}, headers=KEY).status_code == 403
    state["actor"] = TEACHER
    session = private(client.post(f"{path}/sessions", json={"label": "1주"}, headers=KEY)).json()[
        "data"
    ]
    assert session["check_in_code"] == CODE
    state["actor"] = STUDENT
    listed = client.get(f"{path}/sessions").json()["data"]
    assert listed[0]["check_in_code"] is None and CODE not in client.get(f"{path}/sessions").text
    blue = client.post(
        f"{path}/sessions/{session['id']}/check-in", json={"method": "BLUETOOTH", "code": CODE}
    )
    assert blue.status_code == 400
    wrong = private(
        client.post(
            f"{path}/sessions/{session['id']}/check-in",
            json={"method": "DEMO_CODE", "code": "999999"},
        )
    )
    assert wrong.status_code == 400 and wrong.json()["field_errors"] == {"rule": "CODE_MISMATCH"}
    ok = client.post(
        f"{path}/sessions/{session['id']}/check-in", json={"method": "DEMO_CODE", "code": CODE}
    )
    assert ok.json()["data"]["mark"] == "CHECKED_IN"
    assert client.get(f"{path}/sessions/{session['id']}/records").status_code == 403
    state["actor"] = TEACHER
    records = client.get(f"{path}/sessions/{session['id']}/records").json()["data"]
    assert {r["student_label"] for r in records} == {"가상 학생 1", "가상 학생 2"}
    assert str(STUDENT.user_id) not in client.get(f"{path}/sessions/{session['id']}/records").text
    foreign = f"{BASE}/attendance/offerings/{uuid4()}/sessions"
    assert client.get(foreign).status_code == 404


def test_unexpected_failure_is_redacted_and_not_cached(caplog):
    store = seeded_store()

    def broken(*args, **kwargs):
        raise RuntimeError("private-database-password")

    store.unit_of_work = broken
    app = build(STUDENT, make_service(store))
    with caplog.at_level(logging.ERROR, logger="ditnow.api"), TestClient(app) as client:
        response = private(client.get(f"{BASE}/records"))
    assert response.status_code == 500 and "private-database-password" not in response.text
    logs = "\n".join(record.message for record in caplog.records if record.name == "ditnow.api")
    assert "private-database-password" not in logs


def test_openapi_hides_internal_records():
    schemas = build().openapi()["components"]["schemas"]
    for internal in ("EnrollmentRecord", "GradeRecord", "AcademicRequestRecord", "SessionRecord"):
        assert internal not in schemas
    assert "student_id" not in schemas["EnrollmentView"]["properties"]
