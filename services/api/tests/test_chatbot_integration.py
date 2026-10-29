"""TC-V1-CAMP-001 공개 검색 부분 구현 및 통합 경계 회귀 검사."""

import json
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.factory import create_app
from app.integrations.chatbot.campus import get_campus_search


@pytest.fixture
def client() -> Iterator[TestClient]:
    application = create_app(Settings(environment="test"))
    with TestClient(application) as test_client:
        yield test_client


def test_existing_retriever_is_reused_with_provenance(client: TestClient) -> None:
    response = client.get("/api/v1/ai/campus/search", params={"q": "컴소과 사무실"})
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["found"] is True
    assert data["hits"][0]["source_id"] == "dept_cs"
    assert data["verification"] == "UNKNOWN"
    assert data["generated"] is False
    assert data["personal_data_access"] is False
    assert data["mode"] == "retrieval_only"


def test_search_unknown_and_personal_queries_do_not_use_student_data(client: TestClient) -> None:
    for question in ["오늘 날씨", "내 성적 알려줘", "내 학번 알려줘"]:
        response = client.get("/api/v1/ai/campus/search", params={"q": question})
        assert response.status_code == 200
        assert response.json()["data"]["hits"] == []
        assert response.json()["data"]["personal_data_access"] is False


@pytest.mark.parametrize("query", ["", "   ", "???", "가" * 201])
def test_query_validation_uses_common_error(client: TestClient, query: str) -> None:
    response = client.get("/api/v1/ai/campus/search", params={"q": query})
    assert response.status_code == 400
    assert response.json()["code"] == "VALIDATION"
    assert response.json()["request_id"] == response.headers["X-Request-ID"]
    assert "detail" not in response.json()


@pytest.mark.parametrize("limit", ["0", "11", "not-a-number"])
def test_limit_is_bounded(client: TestClient, limit: str) -> None:
    response = client.get("/api/v1/ai/campus/search", params={"q": "도서관", "limit": limit})
    assert response.status_code == 400


def test_response_is_allowlisted_and_never_returns_legacy_identity(client: TestClient) -> None:
    response = client.get("/api/v1/ai/campus/search", params={"q": "도서관", "limit": 1})
    data = response.json()["data"]
    assert len(data["hits"]) <= 1
    for hit in data["hits"]:
        assert set(hit) == {
            "source_id",
            "name",
            "category",
            "text",
            "building",
            "floor",
            "room",
            "hours",
            "score",
            "matched_by",
        }
    assert "student_id" not in response.text
    assert "password_hash" not in response.text
    assert "kakao_id" not in response.text


def test_legacy_login_admin_and_personal_routes_are_not_mounted(client: TestClient) -> None:
    for path in ["/auth/login", "/auth/logout", "/admin/questions", "/admin/reload", "/ask"]:
        assert client.post(path, json={}).status_code == 404
    assert client.post("/api/v1/ai/ask", json={"question": "내 성적"}).status_code == 404


def test_import_and_retrieval_do_not_initialize_legacy_runtime() -> None:
    code = """
import json, sys
from app.integrations.chatbot.campus import get_campus_search
result = get_campus_search().search('컴소과 사무실', 1)
blocked = ['chatbot.app.main', 'chatbot.app.auth', 'chatbot.app.db',
           'chatbot.app.config', 'chatbot.app.llm', 'chatbot.app.student_repo']
assert not any(name in sys.modules for name in blocked)
print(json.dumps({'found': result.found}))
"""
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        check=True,
    )
    assert json.loads(result.stdout) == {"found": True}


def test_index_is_cached_without_storing_questions() -> None:
    first = get_campus_search()
    assert first is get_campus_search()
    assert set(vars(first)) == {"_retriever"}
    first.search("도서관", 1)
    assert set(vars(first)) == {"_retriever"}
