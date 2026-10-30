"""Isolated HTTP tests for the enabled FR-CAMP-002 router; no DB, map or external calls."""

from dataclasses import dataclass

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.factory import create_app
from app.features.campus_travel import CALCULATE_PATH, NOTICE, build_travel_router

URL = f"/api/v1{CALCULATE_PATH}"
BASE = {
    "previous_ends_at": "2026-10-30T10:00:00+09:00",
    "next_starts_at": "2026-10-30T10:15:00+09:00",
    "estimated_travel_minutes": 10,
}
BEFORE = "2026-10-30T09:59:59+09:00"
SAME = BASE["previous_ends_at"]
RESULT_KEYS = {
    "previous_ends_at",
    "next_starts_at",
    "gap_seconds",
    "travel_seconds",
    "remaining_seconds",
    "status",
    "estimate_source",
    "calculation_version",
    "notice",
}


@dataclass(frozen=True)
class SyntheticActor:
    user_id: str


def client_for(**kwargs) -> TestClient:
    app = create_app(Settings(environment="test"))
    app.include_router(build_travel_router(**kwargs), prefix="/api/v1")
    return TestClient(app)


@pytest.fixture
def client():
    with client_for(enabled=True) as value:
        yield value


def post(client: TestClient, **changes):
    return client.post(URL, json={**BASE, **changes})


def test_enabled_post_returns_exact_contract_in_utc(client):
    response = post(client)
    assert response.status_code == 200
    assert response.headers["cache-control"] == "private, no-store"
    data = response.json()["data"]
    assert set(data) == RESULT_KEYS
    assert data == {
        "previous_ends_at": "2026-10-30T01:00:00Z",
        "next_starts_at": "2026-10-30T01:15:00Z",
        "gap_seconds": 900,
        "travel_seconds": 600,
        "remaining_seconds": 300,
        "status": "HAS_MARGIN",
        "estimate_source": "USER_INPUT",
        "calculation_version": "manual-travel-v1",
        "notice": NOTICE,
    }


@pytest.mark.parametrize(
    ("changes", "gap", "remaining", "status"),
    [
        ({"next_starts_at": BEFORE, "estimated_travel_minutes": 0}, -1, -1, "OVERLAP"),
        ({"next_starts_at": "2026-10-30T09:00:00+09:00"}, -3600, -4200, "OVERLAP"),
        ({"estimated_travel_minutes": 20}, 900, -300, "INSUFFICIENT"),
        ({"estimated_travel_minutes": 15}, 900, 0, "NO_MARGIN"),
        ({"next_starts_at": SAME, "estimated_travel_minutes": 0}, 0, 0, "NO_MARGIN"),
    ],
)
def test_overlap_and_margin_states_over_http(client, changes, gap, remaining, status):
    data = post(client, **changes).json()["data"]
    assert (data["gap_seconds"], data["remaining_seconds"], data["status"]) == (
        gap,
        remaining,
        status,
    )


def test_kst_and_utc_inputs_for_the_same_instant_are_equal(client):
    kst = post(
        client,
        previous_ends_at="2026-10-30T23:55:00+09:00",
        next_starts_at="2026-10-31T00:10:00+09:00",
    ).json()["data"]
    utc = post(
        client,
        previous_ends_at="2026-10-30T14:55:00Z",
        next_starts_at="2026-10-30T15:10:00Z",
    ).json()["data"]
    assert kst == utc
    assert kst["gap_seconds"] == 900 and kst["next_starts_at"] == "2026-10-30T15:10:00Z"


def test_kst_year_boundary_normalizes_to_previous_utc_year(client):
    data = post(
        client,
        previous_ends_at="2000-01-01T00:00:00+09:00",
        next_starts_at="2000-01-01T00:15:00+09:00",
    ).json()["data"]
    assert data["previous_ends_at"] == "1999-12-31T15:00:00Z"


def test_seven_day_window_and_minute_bounds_are_inclusive(client):
    response = post(
        client, next_starts_at="2026-11-06T10:00:00+09:00", estimated_travel_minutes=1440
    )
    assert response.status_code == 200
    assert response.json()["data"]["gap_seconds"] == 604800
    backwards = post(client, next_starts_at="2026-10-23T10:00:00+09:00")
    assert backwards.status_code == 200
    assert backwards.json()["data"]["status"] == "OVERLAP"


@pytest.mark.parametrize(
    "body",
    [
        {**BASE, "estimated_travel_minutes": -1},
        {**BASE, "estimated_travel_minutes": 1441},
        {**BASE, "estimated_travel_minutes": 1.5},
        {**BASE, "estimated_travel_minutes": "10"},
        {**BASE, "estimated_travel_minutes": True},
        {**BASE, "next_starts_at": "2026-11-06T10:00:01+09:00"},
        {**BASE, "next_starts_at": "2026-10-23T09:59:59+09:00"},
        {**BASE, "next_starts_at": "2026-10-30T10:15:00"},
        {**BASE, "next_starts_at": "2026-10-30T10:15+09:00"},
        {**BASE, "next_starts_at": "2026-10-30T10:15:00.000+09:00"},
        {**BASE, "next_starts_at": "2026-02-29T10:15:00+09:00"},
        {**BASE, "next_starts_at": "2100-01-01T00:00:00Z"},
        {**BASE, "next_starts_at": 1793322000},
        {key: value for key, value in BASE.items() if key != "estimated_travel_minutes"},
        {**BASE, "distance_meters": 120},
    ],
)
def test_invalid_input_is_rejected_with_common_envelope(client, body):
    response = client.post(URL, json=body)
    assert response.status_code == 400
    assert response.json()["code"] == "VALIDATION"
    assert response.headers["cache-control"] == "private, no-store"


@pytest.mark.parametrize("field", ["user_id", "actor", "department_id", "role", "student_id"])
def test_client_supplied_identity_fields_are_rejected(client, field):
    response = post(client, **{field: "PII_MARKER"})
    assert response.status_code == 400
    assert "PII_MARKER" not in response.text


def test_non_json_and_wrong_method_keep_private_no_store(client):
    malformed = client.post(URL, content=b"{", headers={"Content-Type": "application/json"})
    assert malformed.status_code == 400
    assert malformed.headers["cache-control"] == "private, no-store"
    assert client.get(URL).status_code == 405


def test_disabled_router_fails_closed_even_for_invalid_body():
    with client_for() as closed:
        response = closed.post(URL, json={"private": "PII_MARKER"})
    assert response.status_code == 503
    assert response.json()["code"] == "UNAVAILABLE"
    assert response.headers["cache-control"] == "private, no-store"
    assert "PII_MARKER" not in response.text


def test_injected_actor_requires_server_identity():
    with client_for(enabled=True, actor=lambda: None) as anonymous:
        denied = anonymous.post(URL, json=BASE)
    assert denied.status_code == 401
    assert denied.json()["code"] == "UNAUTHORIZED"
    assert denied.headers["cache-control"] == "private, no-store"
    with client_for(enabled=True, actor=lambda: SyntheticActor("")) as blank:
        assert blank.post(URL, json=BASE).status_code == 401
    with client_for(enabled=True, actor=lambda: SyntheticActor("synthetic-user")) as signed:
        allowed = signed.post(URL, json=BASE)
    assert allowed.status_code == 200
    assert "synthetic-user" not in allowed.text


def test_disabled_router_does_not_resolve_actor():
    def exploding_actor():
        raise AssertionError("actor must not be resolved while disabled")

    with client_for(actor=exploding_actor) as closed:
        assert closed.post(URL, json=BASE).status_code == 503


def test_exported_path_is_mount_ready():
    paths = {route.path for route in build_travel_router(enabled=True).routes}
    assert paths == {CALCULATE_PATH}
