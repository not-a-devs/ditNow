"""TC-DB-CONFIG: offline settings/TLS checks, not live MariaDB validation."""

import asyncio
import json
import ssl
from unittest.mock import AsyncMock, Mock

import aiomysql
import pytest
from pydantic import ValidationError
from pymysql.constants import CLIENT

from app.core import db_connection
from app.core.config import Settings
from app.core.db_connection import (
    DatabaseConfigurationError,
    TLSRequiredConnection,
    configuration_report,
    create_database_engine,
    main,
)


def configured(**changes):
    return Settings(
        environment="test",
        **(
            {
                "db_host": "db.private.invalid",
                "db_user": "ditnow_app",
                "db_password": "fictional-test-secret",
            }
            | changes
        ),
    )


def test_optional_database_is_not_readiness():
    settings = Settings(environment="test")
    report = configuration_report(settings)
    assert not report.configured
    assert report.connection == report.grants == "NOT_RUN"
    assert report.schema_version == "BLOCKED_LEDGER_CONTRACT"
    with pytest.raises(DatabaseConfigurationError, match="not configured"):
        create_database_engine(settings)


@pytest.mark.parametrize(
    "fields",
    [
        {"db_host": "db.private.invalid"},
        {"db_password": "fictional-test-secret"},
        {"db_user": "ditnow_app"},
        {"db_port": 3307},
        {"db_host": "", "db_user": "ditnow_app", "db_password": "fictional-test-secret"},
    ],
)
def test_partial_config_fails_closed_without_secret_in_message(fields):
    with pytest.raises(ValidationError) as error:
        Settings(environment="test", **fields)
    assert "fictional-test-secret" not in str(error.value)


@pytest.mark.parametrize(
    "changes",
    [
        {"db_user": "ditnow_migrator"},
        {"db_user": "root"},
        {"db_name": "ditnow_chatbot"},
        {"db_password": ""},
        {"db_port": 0},
        {"db_connect_timeout": 6},
        {"db_host": "mysql://user:pass@host"},
        {"db_host": "db host"},
        {"db_tls_ca_file": "missing-ca-file.pem"},
    ],
)
def test_runtime_rejects_wrong_accounts_and_unsafe_settings(changes):
    with pytest.raises(ValidationError):
        configured(**changes)


def test_prefixed_environment_and_secret_representation(monkeypatch):
    monkeypatch.setenv("DIT_API_ENVIRONMENT", "test")
    monkeypatch.setenv("DIT_API_DB_HOST", "db.private.invalid")
    monkeypatch.setenv("DIT_API_DB_USER", "ditnow_app")
    monkeypatch.setenv("DIT_API_DB_PASSWORD", "fictional-test-secret")
    settings = Settings()
    assert settings.database_configured
    assert settings.db_port == 3307
    assert "fictional-test-secret" not in repr(settings)
    assert "db.private.invalid" not in repr(settings)
    assert "fictional-test-secret" not in settings.model_dump_json()
    assert "db.private.invalid" not in configuration_report(settings).model_dump_json()


def test_engine_creation_never_connects_or_embeds_credentials(monkeypatch):
    connect = AsyncMock(side_effect=AssertionError("Network is forbidden in this test"))
    monkeypatch.setattr(TLSRequiredConnection, "_connect", connect)
    engine = create_database_engine(configured())
    assert engine.dialect.is_async
    assert engine.sync_engine.hide_parameters
    assert not engine.echo
    assert engine.url.render_as_string() == "mysql+aiomysql://"
    connect.assert_not_called()
    asyncio.run(engine.dispose())


@pytest.mark.parametrize("fails", [False, True])
def test_async_creator_passes_safe_options_and_sanitizes_driver_errors(monkeypatch, fails):
    options = {}
    driver = Mock()
    driver._connect = AsyncMock(
        side_effect=RuntimeError("fictional-test-secret and private host") if fails else None
    )
    driver_factory = Mock(return_value=driver)
    monkeypatch.setattr(db_connection, "TLSRequiredConnection", driver_factory)
    monkeypatch.setattr(db_connection, "create_async_engine", lambda url, **kw: options.update(kw))
    create_database_engine(configured())
    if fails:
        with pytest.raises(DatabaseConfigurationError) as error:
            asyncio.run(options["async_creator"]())
        assert "fictional-test-secret" not in str(error.value)
        assert error.value.__suppress_context__
        driver.close.assert_called_once()
    else:
        assert asyncio.run(options["async_creator"]()) is driver
    kwargs = driver_factory.call_args.kwargs
    assert kwargs["charset"] == "utf8mb4"
    assert kwargs["port"] == 3307
    assert kwargs["user"] == "ditnow_app"
    assert kwargs["connect_timeout"] == 5
    assert kwargs["ssl"].verify_mode == ssl.CERT_REQUIRED
    assert kwargs["ssl"].check_hostname
    assert kwargs["local_infile"] is kwargs["autocommit"] is kwargs["echo"] is False


@pytest.mark.parametrize(
    "capabilities,context",
    [
        (0, ssl.create_default_context()),
        (CLIENT.SSL, None),
        (CLIENT.SSL, ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)),
    ],
)
def test_authentication_rejects_missing_or_unverified_tls(monkeypatch, capabilities, context):
    # Deliberately disable verification in the third fixture, never in production.
    if context is not None and capabilities == CLIENT.SSL:
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
    original = AsyncMock()
    monkeypatch.setattr(aiomysql.Connection, "_request_authentication", original)
    connection = TLSRequiredConnection.__new__(TLSRequiredConnection)
    connection._ssl_context = context
    connection.server_capabilities = capabilities
    connection._writer = None
    with pytest.raises(DatabaseConfigurationError, match="TLS is required"):
        asyncio.run(connection._request_authentication())
    original.assert_not_called()


def test_authentication_delegates_only_after_tls_preconditions(monkeypatch):
    original = AsyncMock()
    monkeypatch.setattr(aiomysql.Connection, "_request_authentication", original)
    connection = TLSRequiredConnection.__new__(TLSRequiredConnection)
    connection._ssl_context = ssl.create_default_context()
    connection.server_capabilities = CLIENT.SSL
    connection._writer = None
    asyncio.run(connection._request_authentication())
    original.assert_awaited_once()


def test_offline_cli_invalid_configuration_does_not_leak(monkeypatch, capsys):
    monkeypatch.setenv("DIT_API_ENVIRONMENT", "test")
    monkeypatch.setenv("DIT_API_DB_PASSWORD", "fictional-test-secret")
    assert main() == 2
    result = capsys.readouterr().out
    assert "fictional-test-secret" not in result
    assert json.loads(result) == {"configuration": "INVALID", "connection": "NOT_RUN"}
