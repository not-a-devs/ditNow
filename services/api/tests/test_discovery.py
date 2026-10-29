"""Public composition tests; all synthetic fixtures, no network/DB/LLM."""

from datetime import date

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.errors import ApiError
from app.factory import create_app
from app.features.discovery.router import router
from app.features.discovery.service import DiscoveryService, get_discovery_service
from app.features.public_campus.models import PublicGuide, PublicSnapshot, SourceEvidence
from app.features.public_campus.service import PublicCampusService
from app.schemas.ai import CampusSearchData, CampusSearchHit
from app.schemas.common import ErrorCode


def guide(index):
    return PublicGuide(
        id=f"demo-{index:03}",
        title=f"가상 도서관 안내 {index}",
        category="campus",
        summary="가상 테스트 설명",
        tags=["library"],
        feature_ids=["FR-WEB-001"],
        sections=[{"heading": "가상 항목", "paragraphs": ["자동 테스트 전용"]}],
        source=SourceEvidence(
            url="https://www.dit.ac.kr/kr/",
            site="university",
            checked_at=date(2026, 10, 30),
            evidence="가상 테스트 근거",
        ),
    )


def hit(index):
    return CampusSearchHit(
        source_id=f"demo-{index:03}",
        name=f"가상 도서관 {index}",
        category="시설",
        text="가상 시설 설명",
        score=1,
        matched_by="alias",
    )


class Facilities:
    def __init__(self, hits=None):
        self.hits = [hit(0)] if hits is None else hits
        self.calls = []

    def search(self, query, limit):
        self.calls.append((query, limit))
        return CampusSearchData(found=bool(self.hits), hits=self.hits[:limit])


def service(count=2, facilities=None):
    guides = PublicCampusService(
        PublicSnapshot(
            version="public-campus-2026-10-30-v1",
            captured_at=date(2026, 10, 30),
            records=[guide(index) for index in range(count)],
        )
    )
    return DiscoveryService(guides, facilities or Facilities())


def test_normalized_combined_pagination_is_stable_and_source_qualities_stay_separate():
    facilities = Facilities()
    search = service(facilities=facilities)
    first = search.search("  ＬＩＢＲＡＲＹ  ", "all", 0, 2)
    second = search.search("library", "all", 2, 2)
    assert first.query == "library"
    assert first.total == 3 and first.counts == {"guide": 2, "facility": 1}
    assert [item.id for item in first.items + second.items] == [
        "facility:demo-000",
        "guide:demo-000",
        "guide:demo-001",
    ]
    assert facilities.calls == [("library", 101), ("library", 101)]
    data = first.model_dump()
    assert data["generated"] is data["personal_data_access"] is False
    assert data["items"][0]["source"]["verification"] == "UNKNOWN"
    assert data["items"][1]["source"]["evidence"]["existence"] == "VERIFIED"
    assert data["items"][1]["source"]["evidence"]["freshness"] == "UNKNOWN"


def test_kind_filter_does_not_query_unselected_facility_source():
    facilities = Facilities()
    page = service(facilities=facilities).search("library", "guide", 0, 20)
    assert page.counts == {"guide": 2, "facility": 0} and facilities.calls == []
    assert all(item.detail_path.startswith("/app/information?guide=") for item in page.items)


def test_guides_include_both_existing_source_pages_and_no_duplicates():
    page = service(100).search("library", "guide", 80, 20)
    assert page.complete and page.total == 100 and len(page.items) == 20
    assert page.items[0].id == "guide:demo-080"


def test_facility_cap_signals_incomplete_collection_and_safe_links():
    facilities = Facilities([hit(index) for index in range(101)])
    page = service(facilities=facilities).search("가상", "facility", 80, 20)
    assert not page.complete and page.total == 100
    assert page.counts == {"guide": 0, "facility": 100}
    assert all(item.detail_path.startswith("/app/ai?q=%EA%B0%80%EC%83%81") for item in page.items)


def test_invalid_or_duplicate_facility_ids_are_not_linked_or_miscounted():
    facilities = Facilities([hit(0), hit(0), hit(1).model_copy(update={"source_id": "../private"})])
    page = service(facilities=facilities).search("가상", "facility", 0, 20)
    assert page.total == 1 and not page.complete


def test_empty_and_out_of_range_page_have_consistent_counts():
    empty = service(facilities=Facilities([])).search("찾을수없는가상어", "all", 0, 8)
    assert empty.items == [] and empty.total == 0
    page = service().search("library", "all", 100, 8)
    assert page.items == [] and page.total == 3


@pytest.mark.parametrize("query", ["", "   ", "???", "\u200b도서관", "x" * 201])
def test_invalid_queries_are_rejected(query):
    with pytest.raises(ApiError) as error:
        service().search(query, "all", 0, 8)
    assert error.value.code == ErrorCode.VALIDATION


@pytest.mark.parametrize(
    "params",
    [
        {},
        {"q": "a", "limit": 21},
        {"q": "a", "offset": -1},
        {"q": "a", "offset": 201},
        {"q": "a", "kind": "personal"},
    ],
)
def test_http_input_uses_common_validation_error(params):
    app = create_app(Settings(environment="test"))
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[get_discovery_service] = service
    with TestClient(app) as client:
        response = client.get("/api/v1/discovery", params=params)
    assert response.status_code == 400
    assert response.json()["code"] == "VALIDATION" and response.json()["request_id"]


def test_http_envelope_is_public_only_and_missing_provider_returns_safe_503():
    app = create_app(Settings(environment="test"))
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[get_discovery_service] = service
    with TestClient(app) as client:
        response = client.get("/api/v1/discovery", params={"q": "library"})
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["total"] == 3 and data["personal_data_access"] is False
        assert not any(
            word in response.text for word in ['"author_id"', '"student_number"', '"email"']
        )

        def unavailable():
            raise ApiError(ErrorCode.UNAVAILABLE)

        app.dependency_overrides[get_discovery_service] = unavailable
        response = client.get("/api/v1/discovery", params={"q": "library"})
        assert response.status_code == 503 and response.json()["code"] == "UNAVAILABLE"


def test_existing_public_source_adapters_are_reused_without_personal_access():
    search = get_discovery_service()
    page = search.search("컴소과 사무실", "facility", 0, 10)
    assert any(item.id == "facility:dept_cs" for item in page.items)
    assert all(item.source.verification == "UNKNOWN" for item in page.items)
    assert page.personal_data_access is page.generated is False
    assert search.search("내 성적 알려줘", "all", 0, 10).items == []
