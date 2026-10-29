"""통합 API의 학번 로그인과 RAG 답변 (/api/v1/auth/*, /api/v1/ai/ask).

가짜 LLM과 메모리 SQLite로 실행한다. 외부 LLM·MariaDB를 호출하지 않는다.
"""

import asyncio
from collections.abc import Iterator

import pytest
from chatbot.app.db import init_db
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.core.config import Settings
from app.factory import create_app
from app.seed_demo import load_demo_mock, seed

SQLITE_MEMORY = "sqlite+aiosqlite:///:memory:"
STUDENT = {"student_id": "20231001", "password": "3000001"}


def make_client(**overrides: object) -> TestClient:
    settings = Settings(environment="test", llm_provider="fake", **overrides)
    return TestClient(create_app(settings))


@pytest.fixture
def client() -> Iterator[TestClient]:
    with make_client(database_url=SecretStr(SQLITE_MEMORY)) as test_client:
        # 메모리 DB는 연결을 공유하므로 앱과 같은 이벤트 루프에서 시드한다
        engine = test_client.app.state.assistant.engine
        test_client.portal.call(init_db, engine, load_demo_mock())
        yield test_client


def login(client: TestClient) -> str:
    response = client.post("/api/v1/auth/login", json=STUDENT)
    assert response.status_code == 200
    return response.json()["data"]["token"]


def ask(client: TestClient, question: str, token: str | None = None, **body: object):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return client.post("/api/v1/ai/ask", json={"question": question, **body}, headers=headers)


def test_campus_question_without_login(client: TestClient) -> None:
    response = ask(client, "컴소과 사무실 어디야")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["intent"] == "campus"
    assert data["found"] is True
    assert "dept_cs" in data["sources"]
    assert data["personal_data_access"] is False


def test_personal_question_requires_login(client: TestClient) -> None:
    data = ask(client, "내 성적 알려줘").json()["data"]
    assert data["need_login"] is True
    assert data["personal_data_access"] is False


def test_login_then_personal_question_reads_own_record(client: TestClient) -> None:
    token = login(client)
    data = ask(client, "내 성적 알려줘", token).json()["data"]
    assert data["intent"] == "grades"
    assert data["need_login"] is False
    assert data["sources"] == ["my_grades"]
    assert data["personal_data_access"] is True


def test_wrong_password_and_bad_token_are_401(client: TestClient) -> None:
    response = client.post("/api/v1/auth/login", json={**STUDENT, "password": "wrong"})
    assert response.status_code == 401
    assert response.json()["code"] == "UNAUTHORIZED"
    assert response.headers["cache-control"] == "private, no-store"
    assert ask(client, "내 성적", "not-a-token").status_code == 401


def test_logout_revokes_token(client: TestClient) -> None:
    token = login(client)
    headers = {"Authorization": f"Bearer {token}"}
    assert client.post("/api/v1/auth/logout", headers=headers).status_code == 200
    assert ask(client, "내 성적", token).status_code == 401


def test_history_rewrites_follow_up(client: TestClient) -> None:
    history = [{"role": "user", "content": "컴소과 사무실 어디야"}]
    response = ask(client, "거기 전화번호는?", history=history)
    assert response.status_code == 200


@pytest.mark.parametrize("question", ["", "   ", "???", "가" * 201])
def test_question_validation(client: TestClient, question: str) -> None:
    response = ask(client, question)
    assert response.status_code == 400
    assert response.json()["code"] == "VALIDATION"


def test_rate_limit() -> None:
    with make_client(ask_rate_limit_per_min=2) as limited:
        assert ask(limited, "도서관 어디야").status_code == 200
        assert ask(limited, "도서관 어디야").status_code == 200
        response = ask(limited, "도서관 어디야")
        assert response.status_code == 429
        assert response.json()["code"] == "RATE_LIMITED"


def test_without_db_campus_works_but_login_is_unavailable() -> None:
    with make_client() as no_db:
        assert ask(no_db, "도서관 어디야").status_code == 200
        assert no_db.post("/api/v1/auth/login", json=STUDENT).status_code == 503
        assert ask(no_db, "내 성적", "some-token").status_code == 503


def test_without_llm_ask_is_unavailable() -> None:
    with TestClient(create_app(Settings(environment="test"))) as no_llm:
        assert ask(no_llm, "도서관 어디야").status_code == 503
        # LLM 없는 공개 검색은 그대로 동작한다
        assert no_llm.get("/api/v1/ai/campus/search", params={"q": "도서관"}).status_code == 200


def test_seed_creates_tables_and_demo_data() -> None:
    assert asyncio.run(seed(SQLITE_MEMORY)) is True
