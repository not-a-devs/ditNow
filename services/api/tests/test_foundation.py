import importlib
import logging
from uuid import UUID

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.core.config import Settings
from app.core.errors import ApiError
from app.factory import create_app
from app.schemas.common import ErrorCode
from app.services.health import get_health


@pytest.fixture
def application():
    return create_app(Settings(environment="test", docs_enabled=True))


@pytest.mark.parametrize("path", ["/health", "/api/v1/health"])
def test_health_and_request_id(application, path):
    with TestClient(application) as client:
        response = client.get(path, headers={"X-Request-ID": "untrusted-secret"})
    assert response.status_code == 200
    assert response.json()["data"] == {"status": "ok", "service": "ditnow-api"}
    assert response.json()["server_time"].endswith("Z")
    assert UUID(response.headers["X-Request-ID"])


def test_app_import(monkeypatch):
    monkeypatch.setenv("DIT_API_ENVIRONMENT", "test")
    assert importlib.import_module("app.main").app.title == "DIT NOW API"


def test_openapi_matches_runtime(application):
    schema = application.openapi()
    assert {"/health", "/api/v1/health", "/api/v1/ai/ask", "/api/v1/auth/login"} <= set(
        schema["paths"]
    )
    assert "ErrorResponse" in schema["components"]["schemas"]
    with TestClient(application) as client:
        assert client.get("/openapi.json").json() == schema


def test_docs_disabled_by_default():
    with TestClient(create_app(Settings(environment="test"))) as client:
        assert client.get("/docs").status_code == 404
        assert client.get("/openapi.json").status_code == 404


def test_missing_environment_fails(monkeypatch):
    monkeypatch.delenv("DIT_API_ENVIRONMENT", raising=False)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_invalid_environment_does_not_echo_input():
    with pytest.raises(ValidationError) as exc:
        Settings(environment="password-secret")
    assert "password-secret" not in str(exc.value)


@pytest.mark.parametrize(
    "origin",
    [
        "*",
        "https://x.test/path",
        "https://user:password-secret@x.test",
        "null",
        "https://x.test:bad",
        "https://x.test\n",
        "https://한글.test",
    ],
)
def test_invalid_cors(origin):
    with pytest.raises(ValidationError) as exc:
        Settings(environment="test", cors_origins=[origin])
    assert "password-secret" not in str(exc.value)


def test_env_loading(monkeypatch):
    monkeypatch.setenv("DIT_API_ENVIRONMENT", "test")
    monkeypatch.setenv("DIT_API_CORS_ORIGINS", '["http://localhost:5173"]')
    assert Settings().cors_origins == ["http://localhost:5173"]


def test_cors_allowlist_and_no_credentials():
    app = create_app(Settings(environment="test", cors_origins=["http://localhost:5173"]))
    with TestClient(app) as client:
        allowed = client.get("/health", headers={"Origin": "http://localhost:5173"})
        denied = client.get("/health", headers={"Origin": "https://evil.test"})
    assert allowed.headers["Access-Control-Allow-Origin"] == "http://localhost:5173"
    assert "Access-Control-Allow-Credentials" not in allowed.headers
    assert "Access-Control-Allow-Origin" not in denied.headers


def test_validation_is_common_and_redacted(application):
    @application.get("/validation")
    def validation(value: int):
        return value

    with TestClient(application) as client:
        response = client.get("/validation?value=password-secret")
    assert response.status_code == 400
    assert response.json()["code"] == "VALIDATION"
    assert response.json()["field_errors"] == {"query": "입력값이 올바르지 않습니다."}
    assert "password-secret" not in response.text
    assert response.json()["request_id"] == response.headers["X-Request-ID"]


@pytest.mark.parametrize("path,status", [("/missing", 404), ("/health", 405)])
def test_http_error_envelope(application, path, status):
    with TestClient(application) as client:
        response = client.post(path) if status == 405 else client.get(path)
    assert response.status_code == status
    if status == 405:
        assert response.headers["Allow"] == "GET"
    assert set(response.json()) == {"code", "message", "field_errors", "retryable", "request_id"}


def test_domain_and_http_details_not_exposed(application):
    @application.get("/domain")
    def domain():
        raise ApiError(ErrorCode.CONFLICT)

    @application.get("/http")
    def http():
        raise HTTPException(403, detail="private-secret")

    with TestClient(application) as client:
        assert client.get("/domain").json()["code"] == "CONFLICT"
        response = client.get("/http")
    assert response.status_code == 403
    assert "private-secret" not in response.text


def test_unhandled_failure_and_logs_are_safe(application, caplog):
    @application.post("/failure/{private_path}")
    def failure(private_path: str):
        raise RuntimeError("database-password-secret")

    with caplog.at_level(logging.INFO, logger="ditnow.api"), TestClient(application) as client:
        response = client.post(
            "/failure/private-path-secret?token=query-secret",
            headers={"Authorization": "Bearer auth-secret", "Cookie": "session=cookie-secret"},
            json={"password": "body-secret"},
        )
    assert response.status_code == 500
    assert response.json()["code"] == "INTERNAL"
    assert UUID(response.json()["request_id"])
    for secret in [
        "database-password-secret",
        "private-path-secret",
        "query-secret",
        "auth-secret",
        "cookie-secret",
        "body-secret",
    ]:
        assert secret not in response.text
        own_logs = "\n".join(r.message for r in caplog.records if r.name == "ditnow.api")
        assert secret not in own_logs
    assert '"event": "request.failed"' in own_logs


def test_repository_probe_contract():
    class Unavailable:
        def is_ready(self) -> bool:
            return False

    with pytest.raises(ApiError) as exc:
        get_health(Unavailable())
    assert exc.value.code == ErrorCode.UNAVAILABLE
