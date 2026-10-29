from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from tests.conftest import FIXTURES, SQLITE_MEMORY


@pytest.fixture
def client() -> Iterator[TestClient]:
    """FakeLLMClient와 픽스처 데이터로 띄운 테스트 서버."""
    settings = Settings(
        _env_file=None,
        llm_provider="fake",
        data_dir=FIXTURES,
        mock_dir=FIXTURES / "mock",
        database_url=SQLITE_MEMORY,  # 시작 시 테이블 생성 + 픽스처 목업 시드
        admin_token="secret",
        rate_limit_per_min=3,
    )
    with TestClient(create_app(settings)) as c:
        yield c


def test_health(client: TestClient) -> None:
    assert client.get("/health").json()["status"] == "ok"


def test_ask(client: TestClient) -> None:
    """질문하면 근거와 함께 답한다."""
    body = client.post("/ask", json={"question": "컴소과 어디야?"}).json()
    assert body["found"] is True and body["sources"] == ["dept_cs"]


def test_ask_not_found(client: TestClient) -> None:
    body = client.post("/ask", json={"question": "오늘 날씨 어때?"}).json()
    assert body["found"] is False and body["sources"] == []


@pytest.mark.parametrize("question", ["", "가" * 201, "???"])
def test_ask_validation(client: TestClient, question: str) -> None:
    """빈 질문·200자 초과·내용 없는 질문은 422."""
    assert client.post("/ask", json={"question": question}).status_code == 422


def test_cache_and_rate_limit(client: TestClient) -> None:
    """같은 질문은 캐시로 응답하고 제한에 세지 않는다. 다른 질문은 분당 3회 제한."""
    for _ in range(5):
        assert client.post("/ask", json={"question": "학식"}).status_code == 200
    assert client.post("/ask", json={"question": "컴소과"}).status_code == 200
    assert client.post("/ask", json={"question": "전기과"}).status_code == 200
    assert client.post("/ask", json={"question": "정보관"}).status_code == 429


def test_facilities(client: TestClient) -> None:
    assert len(client.get("/facilities").json()) == 11
    assert client.get("/facilities/dept_cs").json()["name"] == "컴퓨터소프트웨어과"
    assert client.get("/facilities/nope").status_code == 404


def test_admin_reload(client: TestClient) -> None:
    """토큰이 맞을 때만 데이터를 다시 읽는다."""
    assert client.post("/admin/reload").status_code == 403
    assert client.post("/admin/reload", headers={"X-Admin-Token": "bad"}).status_code == 403
    res = client.post("/admin/reload", headers={"X-Admin-Token": "secret"})
    assert res.json()["status"] == "reloaded"


def test_cors(client: TestClient) -> None:
    """허용된 출처에 CORS 헤더를 붙인다."""
    res = client.options(
        "/ask",
        headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "POST"},
    )
    assert res.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_docs_can_send_token(client: TestClient) -> None:
    """/docs(Swagger)가 토큰을 보내려면 헤더 파라미터가 아닌 보안 스킴으로 선언돼야 한다."""
    spec = client.get("/openapi.json").json()
    assert spec["components"]["securitySchemes"]["HTTPBearer"]["scheme"] == "bearer"
    assert {"HTTPBearer": []} in spec["paths"]["/ask"]["post"]["security"]


def test_question_log(client: TestClient) -> None:
    """질문은 로그에 남고, 관리자만 실패 질문을 볼 수 있다. 학번은 남기지 않는다."""
    client.post("/ask", json={"question": "오늘 날씨 어때?"})
    client.post("/ask", json={"question": "컴소과 어디야?"})
    assert client.get("/admin/questions").status_code == 403
    failed = client.get("/admin/questions", headers={"X-Admin-Token": "secret"}).json()
    assert [q["question"] for q in failed] == ["오늘 날씨 어때?"]
    every = client.get(
        "/admin/questions", params={"only_failed": False}, headers={"X-Admin-Token": "secret"}
    ).json()
    assert len(every) == 2 and "student_id" not in every[0]
