"""HTTP contract for FR-OPP-002 matching routes (TC-V1-OPP-002 partial). Fakes only, no DB."""

from datetime import timedelta
from uuid import UUID

import pytest
from fastapi import Header
from fastapi.testclient import TestClient
from test_opportunity_matching_support import (
    NOW,
    OWNER_SECRET,
    USER_A,
    USER_B,
    FakeCatalog,
    FakeContexts,
    FakeRecruitments,
    make_opportunity,
    make_recruitment,
)

from app.core.config import Settings
from app.core.errors import ApiError
from app.factory import create_app
from app.features.opportunities.dependencies import Principal
from app.features.opportunities.repository import TargetScope
from app.features.opportunity_matching import MatchingDependencies, create_router, router
from app.schemas.common import ErrorCode

API = "/api/v1/me/opportunity-matches"
NO_STORE = "private, no-store"

SCHOOL = make_opportunity(id=UUID("00000000-0000-4000-9000-000000000001"), title="전교 장학")
CSE = make_opportunity(
    id=UUID("00000000-0000-4000-9000-000000000002"),
    title="컴퓨터공학과 전용",
    target_scope=TargetScope("department", ("CSE",)),
)
EE = make_opportunity(
    id=UUID("00000000-0000-4000-9000-000000000003"),
    title="전자공학과 전용",
    target_scope=TargetScope("department", ("EE",)),
)


def mount(feature_router) -> TestClient:
    application = create_app(Settings(environment="test"))
    application.include_router(feature_router, prefix="/api/v1")
    return TestClient(application, raise_server_exceptions=False)


def header_principal(x_test_user: str | None = Header(default=None)) -> Principal:
    if x_test_user is None:
        raise ApiError(ErrorCode.UNAUTHORIZED)
    return Principal(UUID(x_test_user))


def as_user(user: UUID) -> dict[str, str]:
    return {"X-Test-User": str(user)}


@pytest.fixture
def contexts():
    return FakeContexts()


@pytest.fixture
def client(contexts):
    catalog = FakeCatalog([SCHOOL, CSE, EE])
    recruitments = FakeRecruitments([make_recruitment(SCHOOL.id)])
    deps = MatchingDependencies(
        current_principal=header_principal,
        academic_context=lambda: contexts,
        catalog=lambda: catalog,
        recruitments=lambda: recruitments,
        clock=lambda: NOW,
    )
    return mount(create_router(deps))


def assert_error(response, status, code):
    assert response.status_code == status
    assert response.json()["code"] == code
    assert response.headers["cache-control"] == NO_STORE


@pytest.mark.parametrize("path", [API, f"{API}/{SCHOOL.id}/brief"])
def test_default_router_fails_closed_with_no_store(path):
    response = mount(router).get(path, headers=as_user(USER_A))
    assert_error(response, 503, "UNAVAILABLE")


def test_missing_academic_context_provider_is_503_even_with_auth():
    deps = MatchingDependencies(
        current_principal=header_principal, catalog=lambda: FakeCatalog([SCHOOL])
    )
    assert_error(mount(create_router(deps)).get(API, headers=as_user(USER_A)), 503, "UNAVAILABLE")


def test_unauthenticated_is_401(client):
    assert_error(client.get(API), 401, "UNAUTHORIZED")


def test_each_user_sees_only_their_own_context(client, contexts):
    a = client.get(API, headers=as_user(USER_A))
    b = client.get(API, headers=as_user(USER_B))
    assert a.status_code == b.status_code == 200
    assert a.headers["cache-control"] == NO_STORE
    titles_a = [i["opportunity"]["title"] for i in a.json()["data"]["items"]]
    titles_b = [i["opportunity"]["title"] for i in b.json()["data"]["items"]]
    assert set(titles_a) == {"전교 장학", "컴퓨터공학과 전용"}
    assert set(titles_b) == {"전교 장학", "전자공학과 전용"}
    assert a.json()["data"]["context"]["memberships"] == [{"department_code": "CSE", "grade": 2}]
    assert "EE" not in a.text
    assert contexts.calls == [USER_A, USER_B]


def test_query_identity_cannot_override_the_principal(client, contexts):
    response = client.get(
        API, params={"user_id": str(USER_B), "department": "EE"}, headers=as_user(USER_A)
    )
    assert response.status_code == 200
    assert contexts.calls == [USER_A]
    assert "전자공학과 전용" not in response.text


def test_forbidden_without_current_context(client, contexts):
    contexts.table[USER_A] = None
    assert_error(client.get(API, headers=as_user(USER_A)), 403, "FORBIDDEN")


def test_interests_filters_and_provenance_round_trip(client):
    response = client.get(
        API,
        params=[
            ("interest_kind", "scholarship"),
            ("interest_keyword", "전교"),
            ("limit", "1"),
        ],
        headers=as_user(USER_A),
    )
    data = response.json()["data"]
    assert response.status_code == 200
    assert data["items"][0]["opportunity"]["title"] == "전교 장학"
    assert data["next_cursor"] is not None
    assert data["context"]["interest_keywords"] == ["전교"]
    assert data["provenance"]["ai_generated"] is False
    assert data["provenance"]["eligibility_guaranteed"] is False
    assert data["complete"] is True and data["candidate_cap"] == 200
    recruitment = data["items"][0]["recruitment"]
    assert recruitment["status"] == "AVAILABLE" and recruitment["open_count"] == 1
    assert OWNER_SECRET not in response.text

    second = client.get(
        API,
        params=[
            ("interest_kind", "scholarship"),
            ("interest_keyword", "전교"),
            ("limit", "1"),
            ("cursor", data["next_cursor"]),
        ],
        headers=as_user(USER_A),
    )
    assert second.status_code == 200
    assert second.json()["data"]["items"][0]["opportunity"]["title"] == "컴퓨터공학과 전용"
    # The same cursor from another user's ranking does not apply.
    assert_error(
        client.get(API, params={"cursor": data["next_cursor"]}, headers=as_user(USER_B)),
        409,
        "CONFLICT",
    )


@pytest.mark.parametrize(
    "params",
    [
        {"interest_kind": "lottery"},
        {"limit": "0"},
        {"limit": "21"},
        {"cursor": "not-a-cursor"},
        {"interest_keyword": "x" * 21},
        [("interest_keyword", str(n)) for n in range(6)],
    ],
)
def test_validation_errors_are_400_and_no_store(client, params):
    assert_error(client.get(API, params=params, headers=as_user(USER_A)), 400, "VALIDATION")


def test_brief_returns_structured_original_fields(client):
    response = client.get(f"{API}/{CSE.id}/brief", headers=as_user(USER_A))
    assert response.status_code == 200
    assert response.headers["cache-control"] == NO_STORE
    data = response.json()["data"]
    assert data["opportunity"]["id"] == str(CSE.id)
    assert data["opportunity"]["eligibility"] == CSE.eligibility
    assert data["match"]["in_scope"] is True
    assert [s["code"] for s in data["procedure"]][0] == "CHECK_ORIGINAL"
    assert data["cautions"][0]["code"] == "NOT_ELIGIBILITY_DECISION"
    other = client.get(f"{API}/{CSE.id}/brief", headers=as_user(USER_B))
    assert other.json()["data"]["match"]["in_scope"] is False


def test_brief_unknown_and_invalid_ids(client):
    assert_error(
        client.get(f"{API}/00000000-0000-4000-9000-000000000999/brief", headers=as_user(USER_A)),
        404,
        "NOT_FOUND",
    )
    assert_error(client.get(f"{API}/not-a-uuid/brief", headers=as_user(USER_A)), 400, "VALIDATION")


def test_unexpected_adapter_error_is_500_without_detail(contexts):
    class Broken:
        def list_public(self, query, now):
            raise RuntimeError("secret adapter detail")

        def get(self, opportunity_id):
            raise RuntimeError("secret adapter detail")

    deps = MatchingDependencies(
        current_principal=header_principal,
        academic_context=lambda: contexts,
        catalog=lambda: Broken(),
        clock=lambda: NOW + timedelta(seconds=1),
    )
    response = mount(create_router(deps)).get(API, headers=as_user(USER_A))
    assert_error(response, 500, "INTERNAL")
    assert "secret" not in response.text
