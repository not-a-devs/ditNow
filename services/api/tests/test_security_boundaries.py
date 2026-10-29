"""PR28 security review regressions. Fake LLM and in-memory state only; no network/DB/secrets."""

from unittest.mock import AsyncMock

import pytest
from chatbot.app.llm.fake_client import FakeLLMClient
from fastapi.testclient import TestClient
from pydantic import SecretStr, ValidationError

from app.core.config import Settings
from app.factory import create_app
from app.integrations.chatbot import assistant as assistant_module

NO_STORE = "private, no-store"


def _app(**overrides):
    return create_app(Settings(environment="test", llm_provider="fake", **overrides))


# F-02: no-store must follow the route-relative path, not the raw ASGI path.
@pytest.mark.parametrize("root_path", ["", "/backend", "/backend/v2"])
@pytest.mark.parametrize(
    "path,body,expected",
    [
        ("/api/v1/ai/ask", {"question": "도서관"}, 200),
        ("/api/v1/ai/ask", {"question": ""}, 400),
        ("/api/v1/auth/login", {"student_id": "demo", "password": "dummy"}, 503),
        ("/api/v1/auth/logout", {}, 503),
        ("/api/v1/auth/unknown", {}, 404),
        ("/api/v1/ai/ask/extra", {}, 404),
    ],
)
def test_private_routes_are_no_store_under_root_path(root_path, path, body, expected):
    with TestClient(_app(), root_path=root_path) as client:
        response = client.post(f"{root_path}{path}", json=body)
        assert response.status_code == expected
        assert response.headers["cache-control"] == NO_STORE


@pytest.mark.parametrize("root_path", ["", "/backend"])
@pytest.mark.parametrize("path", ["/api/v1/ai/ask/", "/api/v1/auth/login/"])
def test_private_trailing_slash_redirect_is_no_store(root_path, path):
    with TestClient(_app(), root_path=root_path, follow_redirects=False) as client:
        response = client.post(f"{root_path}{path}", json={"question": "도서관"})
        assert response.status_code in {307, 404}
        assert response.headers["cache-control"] == NO_STORE


@pytest.mark.parametrize("root_path", ["", "/backend"])
@pytest.mark.parametrize(
    "method,path",
    [
        ("GET", "/health"),
        ("GET", "/api/v1/ai/campus/search?q=도서관"),
        ("POST", "/api/v1/ai/asking"),
        ("POST", "/api/v1/authx"),
    ],
)
def test_public_and_lookalike_paths_keep_cache_policy(root_path, method, path):
    with TestClient(_app(), root_path=root_path) as client:
        response = client.request(method, f"{root_path}{path}")
        assert "cache-control" not in response.headers


def test_root_path_prefix_is_not_trusted_from_request_path_alone():
    # root_path is a server setting; a client-chosen prefix without it is just an unknown route.
    with TestClient(_app()) as client:
        response = client.post("/backend/api/v1/ai/ask", json={"question": "도서관"})
        assert response.status_code == 404
        assert "cache-control" not in response.headers


# F-03: the integrated LLM config takes only explicit DIT_API_* values.
HOSTILE_ENV = {
    "DATABASE_URL": "mysql+aiomysql://u:sentinel-db@db.invalid/x",
    "ADMIN_TOKEN": "sentinel-admin",
    "DB_AUTO_INIT": "true",
    "LLM_PROVIDER": "anthropic",
    "LLM_MODEL": "sentinel-model",
    "LLM_API_KEY": "sentinel-key",
    "LLM_BASE_URL": "https://sentinel.invalid",
    "RATE_LIMIT_PER_MIN": "1",
}


def test_chatbot_llm_config_ignores_ambient_env_and_dotenv(monkeypatch, tmp_path):
    for key, value in HOSTILE_ENV.items():
        monkeypatch.setenv(key, value)
    (tmp_path / ".env").write_text(
        "\n".join(f"{k}={v}" for k, v in HOSTILE_ENV.items()), encoding="utf-8"
    )
    monkeypatch.chdir(tmp_path)
    captured = []

    def fake_factory(config):
        captured.append(config)
        return FakeLLMClient()

    monkeypatch.setattr(assistant_module, "get_llm_client", fake_factory)
    assistant_module.build_assistant(Settings(environment="test", llm_provider="fake"))
    (config,) = captured
    assert config.llm_provider == "fake"
    assert config.llm_model == "" and config.llm_base_url == ""
    assert config.llm_api_key.get_secret_value() == ""
    assert config.database_url.get_secret_value() == ""
    assert config.admin_token.get_secret_value() == ""
    assert config.db_auto_init is False
    assert config.rate_limit_per_min == 20
    assert "sentinel" not in repr(config)


def test_chatbot_llm_config_passes_explicit_values_and_keeps_validators():
    config = assistant_module.chatbot_llm_settings(
        Settings(
            environment="production",
            llm_provider="openai_compatible",
            llm_model="explicit-model",
            llm_api_key=SecretStr("explicit-key"),
            llm_base_url="https://llm.invalid",
            llm_timeout_sec=5,
        )
    )
    assert (config.llm_provider, config.llm_model, config.llm_base_url) == (
        "openai_compatible",
        "explicit-model",
        "https://llm.invalid",
    )
    assert config.llm_api_key.get_secret_value() == "explicit-key"
    assert config.llm_timeout_sec == 5
    assert "explicit-key" not in repr(config)
    # Init-only source still runs field validators (no model_construct bypass).
    with pytest.raises(ValidationError):
        assistant_module.IntegratedLLMSettings(db_auto_init=True)


@pytest.mark.parametrize("construction", ["direct", "integrated_factory"])
def test_integrated_dotenv_source_cannot_read_a_file_even_before_source_filter(
    monkeypatch, construction
):
    import pydantic_settings.main as settings_main
    from pydantic_settings.sources import DotEnvSettingsSource

    # Construct the API settings before installing the source-construction tripwire. Do not
    # create/read chatbot/.env or depend on whether that real developer file happens to exist.
    explicit = Settings(environment="test", llm_provider="fake")
    constructed = []

    class NoFileDotEnvSource(DotEnvSettingsSource):
        def __init__(self, *args, **kwargs):
            # BaseSettings eagerly constructs this source BEFORE settings_customise_sources.
            # Stop before any I/O if an inherited path reaches the source constructor.
            assert kwargs.get("env_file") is None
            constructed.append(True)
            super().__init__(*args, **kwargs)

        def _read_env_file(self, file_path):
            raise AssertionError("Integrated config must not invoke a dotenv file reader")

    monkeypatch.setattr(settings_main, "DotEnvSettingsSource", NoFileDotEnvSource)
    config = (
        assistant_module.IntegratedLLMSettings(llm_provider="fake")
        if construction == "direct"
        else assistant_module.chatbot_llm_settings(explicit)
    )
    assert constructed == [True]
    assert config.model_config["env_file"] is None
    assert config.model_config["extra"] == "ignore"
    assert config.model_config["hide_input_in_errors"] is True
    assert config.database_url.get_secret_value() == ""
    assert config.admin_token.get_secret_value() == ""


# F-04: the fake provider is a test double, never a deployed provider.
@pytest.mark.parametrize("environment", ["development", "production"])
def test_fake_llm_rejected_outside_test(monkeypatch, environment):
    with pytest.raises(ValidationError):
        Settings(environment=environment, llm_provider="fake")
    monkeypatch.setenv("DIT_API_ENVIRONMENT", environment)
    monkeypatch.setenv("DIT_API_LLM_PROVIDER", "fake")
    with pytest.raises(ValidationError):
        Settings()


def test_fake_llm_allowed_in_test_and_real_provider_config_still_constructs():
    assert Settings(environment="test", llm_provider="fake").llm_provider == "fake"
    assert Settings(environment="production", llm_provider="anthropic").llm_provider == "anthropic"
    assert Settings(environment="production").llm_provider is None


# F-06: logout spends the same per-IP quota before any token revoke/DB write.
def test_logout_is_limited_before_token_revoke(monkeypatch):
    application = _app(
        database_url=SecretStr("sqlite+aiosqlite:///:memory:"), ask_rate_limit_per_min=2
    )
    revoke = AsyncMock(return_value=None)
    monkeypatch.setattr(application.state.assistant, "logout", revoke)
    headers = {"Authorization": "Bearer arbitrary-demo"}
    with TestClient(application) as client:
        for _ in range(2):
            assert client.post("/api/v1/auth/logout", headers=headers).status_code == 200
        response = client.post("/api/v1/auth/logout", headers=headers)
        assert response.status_code == 429
        assert response.headers["cache-control"] == NO_STORE
    assert revoke.await_count == 2


def test_logout_and_ask_share_existing_limit(monkeypatch):
    application = _app(
        database_url=SecretStr("sqlite+aiosqlite:///:memory:"), ask_rate_limit_per_min=2
    )
    monkeypatch.setattr(application.state.assistant, "logout", AsyncMock(return_value=None))
    with TestClient(application) as client:
        assert client.post("/api/v1/auth/logout").status_code == 200
        assert client.post("/api/v1/ai/ask", json={"question": "도서관"}).status_code == 200
        assert client.post("/api/v1/auth/logout").status_code == 429


def test_logout_stays_unavailable_outside_test():
    application = create_app(
        Settings(
            environment="production",
            database_url=SecretStr("mysql+aiomysql://dummy:sentinel@db.invalid/x"),
        )
    )
    with TestClient(application) as client:
        response = client.post("/api/v1/auth/logout", headers={"Authorization": "Bearer x"})
        assert response.status_code == 503
        assert "sentinel" not in response.text
