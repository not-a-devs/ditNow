"""PR39 regression checks. No network, real credentials, or persistent DB files."""

from unittest.mock import AsyncMock, Mock

import pytest
from chatbot.app.db import DatabaseNotReady
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.core.config import Settings
from app.core.errors import ApiError
from app.factory import create_app
from app.integrations.chatbot import assistant as assistant_module
from app.schemas.common import ErrorCode
from app.seed_demo import seed


@pytest.mark.parametrize("environment", ["development", "production"])
@pytest.mark.parametrize(
    "url",
    [
        "mysql+aiomysql://dummy:sentinel-password@invalid.example:3307/ditnow",
        "sqlite+aiosqlite:///:memory:",
        "sqlite+aiosqlite:///:memory:?uri=true&mode=rwc",
    ],
)
def test_no_legacy_db_activation_without_common_identity_bridge(monkeypatch, environment, url):
    factory = Mock(side_effect=AssertionError("must not construct legacy engine"))
    monkeypatch.setattr(assistant_module, "make_engine", factory)
    settings = Settings(environment=environment, database_url=SecretStr(url), llm_provider="fake")
    with TestClient(create_app(settings)) as client:
        assert client.get("/health").status_code == 200
        for path, body, headers in [
            ("/api/v1/auth/login", {"student_id": "demo", "password": "dummy"}, {}),
            ("/api/v1/auth/logout", {}, {"Authorization": "Bearer dummy"}),
            ("/api/v1/ai/ask", {"question": "내 성적"}, {"Authorization": "Bearer dummy"}),
        ]:
            response = client.post(path, json=body, headers=headers)
            assert response.status_code == 503
            assert response.headers["cache-control"] == "private, no-store"
            assert "sentinel-password" not in response.text
    factory.assert_not_called()


@pytest.mark.parametrize(
    "url",
    [
        "mysql+aiomysql://dummy:sentinel-password@invalid.example:3307/ditnow",
        "sqlite+aiosqlite:///:memory:?uri=true&mode=rwc",
        "sqlite+aiosqlite:///not-created.db",
    ],
)
def test_api_seed_rejects_noncanonical_memory_before_engine_creation(monkeypatch, url):
    import asyncio

    factory = Mock(side_effect=AssertionError("must not construct engine"))
    monkeypatch.setattr("app.seed_demo.make_engine", factory)
    with pytest.raises(DatabaseNotReady) as exc:
        asyncio.run(seed(url))
    assert "sentinel-password" not in str(exc.value)
    factory.assert_not_called()


def test_invalid_tokens_are_limited_before_db_lookup(monkeypatch):
    settings = Settings(environment="test", llm_provider="fake", ask_rate_limit_per_min=2)
    application = create_app(settings)
    lookup = AsyncMock(side_effect=ApiError(ErrorCode.UNAUTHORIZED))
    monkeypatch.setattr(application.state.assistant, "student_id", lookup)
    with TestClient(application) as client:
        for _ in range(2):
            assert (
                client.post(
                    "/api/v1/ai/ask",
                    json={"question": "도서관"},
                    headers={"Authorization": "Bearer invalid-demo"},
                ).status_code
                == 401
            )
        response = client.post(
            "/api/v1/ai/ask",
            json={"question": "도서관"},
            headers={"Authorization": "Bearer invalid-demo"},
        )
        assert response.status_code == 429
        assert response.headers["cache-control"] == "private, no-store"
        assert lookup.await_count == 2


@pytest.mark.parametrize(
    "path,body,expected",
    [
        ("/api/v1/ai/ask", {"question": "도서관"}, 200),
        ("/api/v1/ai/ask", {"question": ""}, 400),
        ("/api/v1/auth/login", {}, 503),
        ("/api/v1/auth/login", {"student_id": "demo", "password": "dummy"}, 503),
        ("/api/v1/auth/logout", {}, 503),
    ],
)
def test_sensitive_success_and_error_responses_are_not_cacheable(path, body, expected):
    with TestClient(create_app(Settings(environment="test", llm_provider="fake"))) as client:
        response = client.post(path, json=body)
        assert response.status_code == expected
        assert response.headers["cache-control"] == "private, no-store"


def test_sensitive_unhandled_error_is_not_cacheable_or_logged_with_secret(monkeypatch, caplog):
    application = create_app(Settings(environment="test", llm_provider="fake"))
    monkeypatch.setattr(
        application.state.assistant, "ask", AsyncMock(side_effect=RuntimeError("sentinel-secret"))
    )
    with TestClient(application) as client:
        response = client.post("/api/v1/ai/ask", json={"question": "도서관"})
        assert response.status_code == 500
        assert response.headers["cache-control"] == "private, no-store"
        assert "sentinel-secret" not in response.text
    assert "sentinel-secret" not in caplog.text


def test_public_health_cache_is_not_changed():
    with TestClient(create_app(Settings(environment="test"))) as client:
        assert "cache-control" not in client.get("/health").headers


def test_login_body_validation_is_not_cacheable_when_test_session_is_available():
    settings = Settings(environment="test", database_url=SecretStr("sqlite+aiosqlite:///:memory:"))
    with TestClient(create_app(settings)) as client:
        response = client.post("/api/v1/auth/login", json={})
        assert response.status_code == 400
        assert response.headers["cache-control"] == "private, no-store"
