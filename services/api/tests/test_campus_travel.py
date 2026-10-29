import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.core.config import Settings
from app.factory import create_app
from app.features.campus_travel.models import TravelInput
from app.features.campus_travel.router import build_travel_router
from app.features.campus_travel.service import calculate_travel

BASE = {
    "previous_ends_at": "2026-10-30T10:00:00+09:00",
    "next_starts_at": "2026-10-30T10:15:00+09:00",
    "estimated_travel_minutes": 10,
}


@pytest.mark.parametrize(
    ("next_time", "minutes", "gap", "remaining", "status"),
    [
        ("10:15:00", 10, 900, 300, "HAS_MARGIN"),
        ("10:15:00", 20, 900, -300, "INSUFFICIENT"),
        ("10:15:00", 15, 900, 0, "NO_MARGIN"),
        ("09:59:59", 0, -1, -1, "OVERLAP"),
        ("10:00:00", 0, 0, 0, "NO_MARGIN"),
        ("10:00:00", 1, 0, -60, "INSUFFICIENT"),
        ("10:00:01", 0, 1, 1, "HAS_MARGIN"),
    ],
)
def test_exact_seconds_and_same_instant(next_time, minutes, gap, remaining, status):
    result = calculate_travel(
        TravelInput(
            **{
                **BASE,
                "next_starts_at": f"2026-10-30T{next_time}+09:00",
                "estimated_travel_minutes": minutes,
            }
        )
    )
    assert (result.gap_seconds, result.remaining_seconds, result.status) == (gap, remaining, status)
    assert result.estimate_source == "USER_INPUT"
    assert result.previous_ends_at.isoformat() == "2026-10-30T01:00:00+00:00"


def test_dates_offsets_and_boundary_are_actual_elapsed_time():
    result = calculate_travel(
        TravelInput(
            **{
                **BASE,
                "previous_ends_at": "2026-10-30T23:55:00+09:00",
                "next_starts_at": "2026-10-30T15:10:00Z",
            }
        )
    )
    assert result.gap_seconds == 900
    edge = calculate_travel(
        TravelInput(
            **{
                **BASE,
                "next_starts_at": "2026-11-06T10:00:00+09:00",
                "estimated_travel_minutes": 1440,
            }
        )
    )
    assert edge.gap_seconds == 604800 and edge.travel_seconds == 86400


@pytest.mark.parametrize("minutes", [-1, 1441, True, 1.5, "10", None])
def test_minutes_are_bounded_strict_integers(minutes):
    with pytest.raises(ValidationError):
        TravelInput(**{**BASE, "estimated_travel_minutes": minutes})


@pytest.mark.parametrize(
    "time",
    [
        "2026-10-30T10:00:00",
        "2026-10-30",
        "2026-02-30T10:00:00Z",
        "2026-10-30T10:00:00.5Z",
        1793322000,
        "1999-10-30T10:00:00Z",
        "2026-11-06T10:00:01+09:00",
    ],
)
def test_invalid_dates_implicit_zones_and_excessive_window(time):
    with pytest.raises(ValidationError):
        TravelInput(**{**BASE, "next_starts_at": time})


def test_unknown_fields_and_identity_injection_are_not_accepted():
    with pytest.raises(ValidationError):
        TravelInput(**BASE, student_id="private-student")


def test_router_closed_and_no_global_mount():
    app = create_app(Settings(environment="test"))
    assert "/api/v1/campus-travel/calculate" not in app.openapi()["paths"]
    app.include_router(build_travel_router(), prefix="/api/v1")
    with TestClient(app) as client:
        response = client.post("/api/v1/campus-travel/calculate", json=BASE)
    assert response.status_code == 503
    assert response.headers["cache-control"] == "private, no-store"


def test_http_contract_validation_cache_and_no_input_logging(caplog):
    app = create_app(Settings(environment="test"))
    app.include_router(build_travel_router(enabled=True), prefix="/api/v1")
    with TestClient(app) as client:
        response = client.post("/api/v1/campus-travel/calculate", json=BASE)
        invalid = client.post(
            "/api/v1/campus-travel/calculate", json={**BASE, "private": "PII_MARKER"}
        )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["remaining_seconds"] == 300
    assert data["previous_ends_at"] == "2026-10-30T01:00:00Z"
    assert data["estimate_source"] == "USER_INPUT"
    assert invalid.status_code == 400 and invalid.json()["code"] == "VALIDATION"
    for item in (response, invalid):
        assert item.headers["cache-control"] == "private, no-store"
    assert "PII_MARKER" not in invalid.text + caplog.text
    assert BASE["previous_ends_at"] not in caplog.text


def test_unexpected_failure_has_private_cache_and_no_raw_error(monkeypatch):
    def broken(_):
        raise RuntimeError("PRIVATE_EXCEPTION_MARKER")

    monkeypatch.setattr("app.features.campus_travel.router.calculate_travel", broken)
    app = create_app(Settings(environment="test"))
    app.include_router(build_travel_router(enabled=True), prefix="/api/v1")
    with TestClient(app) as client:
        response = client.post("/api/v1/campus-travel/calculate", json=BASE)
    assert response.status_code == 500
    assert response.headers["cache-control"] == "private, no-store"
    assert "PRIVATE_EXCEPTION_MARKER" not in response.text
