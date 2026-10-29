import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.core.config import Settings
from app.factory import create_app
from app.features.public_campus.models import PublicSnapshot, SourceEvidence
from app.features.public_campus.router import router
from app.features.public_campus.service import get_public_campus_service


@pytest.fixture
def client() -> Iterator[TestClient]:
    application = create_app(Settings(environment="test"))
    application.include_router(router, prefix="/api/v1")
    with TestClient(application) as test_client:
        yield test_client


def test_snapshot_covers_six_partial_requirements_with_evidence() -> None:
    snapshot = PublicSnapshot.model_validate_json(
        (Path(__file__).parents[1] / "app/features/public_campus/snapshot.json").read_text(
            encoding="utf-8"
        )
    )
    assert {feature for record in snapshot.records for feature in record.feature_ids} == {
        "FR-WEB-001",
        "FR-WEB-002",
        "FR-WEB-003",
        "FR-WEB-004",
        "FR-DEPT-007",
        "FR-DEPT-008",
    }
    assert len(snapshot.records) == 7
    for record in snapshot.records:
        assert record.source.checked_at.isoformat() == "2026-10-30"
        assert record.source.existence == "VERIFIED"
        assert record.source.processing_rules == "PARTIAL"
        assert record.source.freshness == "UNKNOWN"
        assert record.content_kind == "EDITORIAL_PUBLIC_SUMMARY"


def test_list_search_category_and_source_filters(client: TestClient) -> None:
    all_records = client.get("/api/v1/public-campus").json()["data"]
    assert all_records["total"] == 7
    result = client.get("/api/v1/public-campus", params={"q": "　컴퓨터소프트웨어　", "site": "cs"})
    assert result.status_code == 200
    assert result.json()["data"]["total"] >= 1
    filtered = client.get(
        "/api/v1/public-campus", params={"category": "disclosure", "site": "university"}
    ).json()["data"]
    assert filtered["total"] == 1
    assert filtered["items"][0]["id"] == "information-disclosure"
    assert "sections" not in filtered["items"][0]


def test_pagination_is_stable_and_empty_search_is_honest(client: TestClient) -> None:
    first = client.get("/api/v1/public-campus", params={"limit": 2}).json()["data"]
    second = client.get("/api/v1/public-campus", params={"limit": 2, "offset": 2}).json()["data"]
    assert first["total"] == second["total"] == 7
    assert not ({item["id"] for item in first["items"]} & {item["id"] for item in second["items"]})
    empty = client.get("/api/v1/public-campus", params={"q": "this-does-not-exist"}).json()["data"]
    assert empty["items"] == [] and empty["total"] == 0
    assert client.get("/api/v1/public-campus", params={"offset": 100}).json()["data"]["items"] == []


def test_detail_contains_native_summary_body_and_source(client: TestClient) -> None:
    response = client.get("/api/v1/public-campus/cs-study-fields")
    assert response.status_code == 200
    detail = response.json()["data"]
    assert detail["summary"] and detail["sections"][0]["paragraphs"]
    assert detail["source"]["url"].startswith("https://www.dit.ac.kr/cs/")
    assert detail["source"]["checked_scope"]
    assert response.headers["X-Request-ID"]


def test_mutating_returned_record_does_not_change_snapshot() -> None:
    service = get_public_campus_service()
    record = service.get_guide("cs-study-fields")
    original = record.title
    record.title = "must-not-persist"
    assert service.get_guide("cs-study-fields").title == original


@pytest.mark.parametrize(
    "query",
    [
        {"limit": 0},
        {"limit": 51},
        {"offset": -1},
        {"category": "private"},
        {"site": "other"},
        {"q": "x" * 201},
    ],
)
def test_input_limits_use_common_errors(client: TestClient, query: dict[str, object]) -> None:
    response = client.get("/api/v1/public-campus", params=query)
    assert response.status_code == 400
    assert response.json()["code"] == "VALIDATION"


def test_missing_and_write_routes_do_not_claim_authority(client: TestClient) -> None:
    response = client.get("/api/v1/public-campus/not-found")
    assert response.status_code == 404 and response.json()["code"] == "NOT_FOUND"
    for method in ["post", "put", "delete", "patch"]:
        assert getattr(client, method)("/api/v1/public-campus/cs-study-fields").status_code == 405


@pytest.mark.parametrize(
    "url",
    [
        "http://www.dit.ac.kr/kr/",
        "https://evil.example/kr/",
        "https://u:p@www.dit.ac.kr/kr/",
        "https://www.dit.ac.kr/kr/?token=secret",
        "https://www.dit.ac.kr/kr/?token=",
        "https://www.dit.ac.kr/kr/#secret",
        "https://www.dit.ac.kr:443/kr/",
        "https://www.dit.ac.kr/private/",
    ],
)
def test_source_url_allowlist_rejects_credentials_and_unapproved_pages(url: str) -> None:
    with pytest.raises(ValidationError):
        SourceEvidence(url=url, site="university", checked_at="2026-10-30", evidence="Test source")


def test_snapshot_rejects_duplicates_future_evidence_and_wrong_site() -> None:
    path = Path(__file__).parents[1] / "app/features/public_campus/snapshot.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["records"].append(raw["records"][0])
    with pytest.raises(ValidationError, match="unique"):
        PublicSnapshot.model_validate(raw)
    raw["records"].pop()
    raw["records"][0]["source"]["checked_at"] = "2026-10-31"
    with pytest.raises(ValidationError, match="Evidence"):
        PublicSnapshot.model_validate(raw)
    with pytest.raises(ValidationError, match="match"):
        SourceEvidence(
            url="https://www.dit.ac.kr/cs/",
            site="university",
            checked_at="2026-10-30",
            evidence="Test",
        )


def test_unmounted_module_is_not_published_in_openapi() -> None:
    assert (
        "/api/v1/public-campus" not in create_app(Settings(environment="test")).openapi()["paths"]
    )
