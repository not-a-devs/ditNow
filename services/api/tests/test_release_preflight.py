"""Synthetic settings only: no operator environment, credentials, network, DB or LLM calls."""

import json
import os
from uuid import uuid4

import pytest

from app.core.config import Settings
from app.operations import release_preflight as check


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    # Do not inspect values or use a real secret store. Isolate all DIT settings from the test.
    for key in tuple(os.environ):
        if key.startswith("DIT_API_"):
            monkeypatch.delenv(key)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DIT_API_ENVIRONMENT", "production")


def configured(**changes):
    return Settings(
        **(
            {
                "environment": "production",
                "p0_runtime_enabled": True,
                "p0_schema_approved": True,
                "p0_identity_approval_ids": [uuid4(), uuid4()],
                "db_host": "db.synthetic.invalid",
                "db_user": "ditnow_app",
                "db_password": "synthetic-private-password",
            }
            | changes
        )
    )


def assert_offline(report):
    assert (
        report.deployment
        == report.db_connection
        == report.db_schema
        == report.db_grants
        == "NOT_RUN"
    )
    assert (
        report.db_certificate_pin
        == report.ingress_spa_https
        == report.host_proxy_workers
        == "NOT_VERIFIED"
    )
    assert report.llm_approval_and_call == "NOT_RUN"
    assert report.identity_approvals == "NOT_VERIFIED"


def test_public_profile_is_config_only_and_does_not_need_database():
    report = check.inspect_settings(Settings(), "public")
    assert report.configuration == "PASS" and report.codes == ()
    assert_offline(report)


def test_p0_missing_configuration_fails_and_uses_existing_database_report(monkeypatch):
    original = check.configuration_report
    calls = []

    def reused(settings):
        calls.append(settings)
        return original(settings)

    monkeypatch.setattr(check, "configuration_report", reused)
    settings = Settings()
    report = check.inspect_settings(settings, "p0")
    assert calls == [settings]
    assert report.configuration == "FAIL"
    assert set(report.codes) == {
        "P0_RUNTIME_DISABLED",
        "P0_DATABASE_CONFIGURATION_MISSING",
        "P0_SCHEMA_ATTESTATION_MISSING",
        "P0_IDENTITY_APPROVAL_PINS_MISSING",
    }
    assert_offline(report)


def test_complete_p0_configuration_does_not_verify_pins_schema_grants_or_tls():
    report = check.inspect_settings(configured(), "p0")
    assert report.configuration == "PASS" and report.codes == ()
    assert_offline(report)


@pytest.mark.parametrize(
    ("changes", "code"),
    [
        ({"environment": "development"}, "PRODUCTION_ENVIRONMENT_REQUIRED"),
        ({"docs_enabled": True}, "DOCS_EXPOSURE_REVIEW_REQUIRED"),
        ({"cors_origins": ["http://example.invalid"]}, "HTTPS_CORS_REVIEW_REQUIRED"),
        (
            {"database_url": "mysql://synthetic-secret@synthetic.invalid/db"},
            "LEGACY_DATABASE_URL_UNSUPPORTED",
        ),
        ({"ask_rate_limit_per_min": 0}, "POSITIVE_RATE_LIMIT_REQUIRED"),
        ({"ask_rate_limit_per_min": -1}, "POSITIVE_RATE_LIMIT_REQUIRED"),
        ({"p0_runtime_enabled": False}, "P0_RUNTIME_DISABLED"),
        ({"p0_schema_approved": False}, "P0_SCHEMA_ATTESTATION_MISSING"),
        ({"p0_identity_approval_ids": []}, "P0_IDENTITY_APPROVAL_PINS_MISSING"),
        ({"llm_model": "synthetic-model"}, "ORPHAN_LLM_CONFIGURATION"),
        ({"llm_api_key": "synthetic-api-secret"}, "ORPHAN_LLM_CONFIGURATION"),
        ({"llm_base_url": "https://synthetic.invalid"}, "ORPHAN_LLM_CONFIGURATION"),
        ({"llm_provider": "openai"}, "LLM_MODEL_MISSING"),
        ({"llm_provider": "anthropic", "llm_model": "synthetic-model"}, "LLM_API_KEY_MISSING"),
        (
            {"llm_provider": "openai_compatible", "llm_model": "synthetic-model"},
            "LLM_COMPATIBLE_BASE_URL_MISSING",
        ),
        (
            {
                "llm_provider": "openai_compatible",
                "llm_model": "synthetic-model",
                "llm_base_url": "https://synthetic.invalid",
                "llm_timeout_sec": 0,
            },
            "POSITIVE_FINITE_LLM_TIMEOUT_REQUIRED",
        ),
        (
            {
                "llm_provider": "openai_compatible",
                "llm_model": "synthetic-model",
                "llm_base_url": "https://synthetic.invalid",
                "llm_timeout_sec": float("nan"),
            },
            "POSITIVE_FINITE_LLM_TIMEOUT_REQUIRED",
        ),
    ],
)
def test_detects_contradictions_without_exposing_values(changes, code):
    report = check.inspect_settings(configured(**changes), "p0")
    assert report.configuration == "FAIL" and code in report.codes
    encoded = json.dumps(check.asdict(report))
    assert "synthetic" not in encoded


def test_profile_mismatch_duplicate_pins_and_exact_https_origins():
    assert "PUBLIC_PROFILE_HAS_P0_RUNTIME" in check.inspect_settings(configured(), "public").codes
    pin = uuid4()
    assert (
        "P0_IDENTITY_APPROVAL_PINS_DUPLICATED"
        in check.inspect_settings(configured(p0_identity_approval_ids=[pin, pin]), "p0").codes
    )
    assert (
        check.inspect_settings(
            configured(cors_origins=["https://web.synthetic.invalid"]), "p0"
        ).configuration
        == "PASS"
    )


def test_keyless_compatible_configuration_is_not_llm_or_cost_approval():
    report = check.inspect_settings(
        configured(
            llm_provider="openai_compatible",
            llm_model="synthetic-model",
            llm_base_url="https://model.synthetic.invalid",
        ),
        "p0",
    )
    assert report.configuration == "PASS"
    assert report.llm_approval_and_call == "NOT_RUN"


def test_complete_p0_cli_output_contains_no_values_or_authority_claim(monkeypatch, capsys):
    pins = [str(uuid4()), str(uuid4())]
    for key, value in {
        "DIT_API_DB_HOST": "db.synthetic.invalid",
        "DIT_API_DB_USER": "ditnow_app",
        "DIT_API_DB_PASSWORD": "synthetic-password-private",
        "DIT_API_P0_RUNTIME_ENABLED": "true",
        "DIT_API_P0_SCHEMA_APPROVED": "true",
        "DIT_API_P0_IDENTITY_APPROVAL_IDS": json.dumps(pins),
    }.items():
        monkeypatch.setenv(key, value)
    assert check.main(["--profile", "p0"]) == 0
    output = capsys.readouterr().out
    assert "synthetic" not in output and "ditnow_app" not in output
    assert all(pin not in output for pin in pins)
    report = json.loads(output)
    assert report["configuration"] == "PASS" and report["identity_approvals"] == "NOT_VERIFIED"


def test_cli_uses_fixed_safe_output_and_never_opens_network_or_dotenv(
    monkeypatch, capsys, tmp_path
):
    import socket

    from pydantic_settings.sources import DotEnvSettingsSource, SecretsSettingsSource

    def forbidden(*_args, **_kwargs):
        raise AssertionError("Network/secret file access forbidden")

    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(DotEnvSettingsSource, "_read_env_file", forbidden)
    monkeypatch.setattr(SecretsSettingsSource, "get_field_value", forbidden)
    # env_file/secrets_dir are None: source construction is not a file read.
    (tmp_path / ".env").write_text("DIT_API_DB_PASSWORD=synthetic-dotenv-secret", encoding="utf-8")
    assert check.main(["--profile", "public"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["configuration"] == "PASS" and result["deployment"] == "NOT_RUN"


@pytest.mark.parametrize(
    "argv",
    [
        [],
        ["--profile", "synthetic-argument-secret"],
        ["--profile", "public", "--password", "synthetic-argument-secret"],
    ],
)
def test_invalid_arguments_cannot_echo_secrets(argv, capsys):
    assert check.main(argv) == 2
    captured = capsys.readouterr()
    assert "synthetic" not in captured.out + captured.err
    assert json.loads(captured.out)["codes"] == ["INVALID_ARGUMENTS"]


@pytest.mark.parametrize(
    "environment",
    [
        {"DIT_API_DB_PASSWORD": "synthetic-invalid-secret"},
        {"DIT_API_DB_USER": "ditnow_migrator"},
        {"DIT_API_LLM_PROVIDER": "fake"},
        {"DIT_API_CORS_ORIGINS": '["https://user:synthetic-invalid-secret@example.invalid"]'},
        {"DIT_API_P0_IDENTITY_APPROVAL_IDS": '["synthetic-invalid-secret"]'},
    ],
)
def test_settings_failure_is_safe_and_uses_existing_validation(environment, monkeypatch, capsys):
    for key, value in environment.items():
        monkeypatch.setenv(key, value)
    assert check.main(["--profile", "p0"]) == 2
    captured = capsys.readouterr()
    assert "synthetic" not in captured.out + captured.err
    assert json.loads(captured.out)["codes"] == ["SETTINGS_INVALID"]
