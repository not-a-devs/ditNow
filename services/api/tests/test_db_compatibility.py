"""No network: dialect event ordering and Windows loop selection regression checks."""

import asyncio
from unittest.mock import Mock

import pytest
from uvicorn import Config

from app.core import event_loop
from app.core.db_connection import (
    SESSION_CHARSET_SQL,
    DatabaseConfigurationError,
    _configure_connection_charset,
    create_database_engine,
)
from tests.test_db_configuration import configured


def test_collation_is_restored_after_actual_dialect_connection_initializer(monkeypatch):
    engine = create_database_engine(configured())
    statements = []
    cursor = Mock()
    cursor.execute.side_effect = statements.append
    connection = Mock()
    connection.character_set_name.return_value = "utf8mb4"
    connection.cursor.return_value = cursor
    # The dialect's separate server-version discovery would issue metadata queries.
    # Skip that discovery, but preserve its REAL on_connect SET NAMES listener.
    monkeypatch.setattr(engine.dialect, "initialize", Mock())
    engine.sync_engine.pool.dispatch.connect(connection, None)
    assert statements == ["SET NAMES utf8mb4", SESSION_CHARSET_SQL]
    assert cursor.close.call_count == 2
    asyncio.run(engine.dispose())


@pytest.mark.parametrize("stage", ["cursor", "execute", "close"])
def test_charset_initialization_failure_is_closed_and_secret_safe(stage):
    cursor = Mock()
    connection = Mock()
    connection.cursor.return_value = cursor
    target = connection.cursor if stage == "cursor" else getattr(cursor, stage)
    target.side_effect = RuntimeError("private-host fictional-password")
    with pytest.raises(DatabaseConfigurationError) as exc:
        _configure_connection_charset(connection, None)
    assert "private-host" not in str(exc.value) and "fictional-password" not in str(exc.value)
    assert exc.value.__suppress_context__
    assert cursor.close.call_count == (0 if stage == "cursor" else 1)


def test_windows_factory_creates_selector_without_replacing_global_policy(monkeypatch):
    monkeypatch.setattr(event_loop, "platform", "win32")
    policy = asyncio.get_event_loop_policy()
    loop = event_loop.new_event_loop()
    try:
        assert isinstance(loop, asyncio.SelectorEventLoop)
        assert asyncio.get_event_loop_policy() is policy
    finally:
        loop.close()


def test_unix_factory_keeps_default_loop_constructor(monkeypatch):
    monkeypatch.setattr(event_loop, "platform", "linux")
    expected = object()
    constructor = Mock(return_value=expected)
    monkeypatch.setattr(event_loop.asyncio, "new_event_loop", constructor)
    assert event_loop.new_event_loop() is expected
    constructor.assert_called_once_with()


def test_installed_uvicorn_custom_loop_callable_returns_a_loop_without_network():
    factory = Config("app.main:app", loop="app.core.event_loop:new_event_loop").get_loop_factory()
    assert factory is event_loop.new_event_loop
    loop = factory()
    try:
        assert isinstance(loop, asyncio.AbstractEventLoop)
    finally:
        loop.close()
