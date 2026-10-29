import ast
import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, Mock

import pytest
from sqlalchemy import event, inspect, text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from app.db import crud_probe as probe
from app.db.models import Base


@pytest.mark.parametrize(
    "flags", [{}, {"DIT_API_RUN_CRUD_PROBE": "1"}, {"DIT_API_CRUD_PROBE_SAFETY_REVIEWED": "1"}]
)
def test_default_or_missing_review_never_reads_configuration_or_connects(
    monkeypatch, capsys, flags
):
    for name in ("DIT_API_RUN_CRUD_PROBE", "DIT_API_CRUD_PROBE_SAFETY_REVIEWED"):
        monkeypatch.delenv(name, raising=False)
    for name, value in flags.items():
        monkeypatch.setenv(name, value)
    settings = Mock(side_effect=AssertionError("settings forbidden"))
    factory = Mock(side_effect=AssertionError("network forbidden"))
    monkeypatch.setattr(probe, "Settings", settings)
    monkeypatch.setattr(probe, "create_database_engine", factory)
    assert probe.main() == 2
    assert json.loads(capsys.readouterr().out)["status"] == "NOT_RUN"
    settings.assert_not_called()
    factory.assert_not_called()


def test_unconfigured_database_never_constructs_engine(monkeypatch, capsys):
    monkeypatch.setenv("DIT_API_RUN_CRUD_PROBE", "1")
    monkeypatch.setenv("DIT_API_CRUD_PROBE_SAFETY_REVIEWED", "1")
    monkeypatch.setattr(probe, "Settings", lambda: Mock(database_configured=False))
    factory = Mock(side_effect=AssertionError("network forbidden"))
    monkeypatch.setattr(probe, "create_database_engine", factory)
    assert probe.main() == 2
    assert json.loads(capsys.readouterr().out)["reason"] == "DATABASE_NOT_CONFIGURED"
    factory.assert_not_called()


def test_configuration_failure_never_prints_secret(monkeypatch, capsys):
    monkeypatch.setenv("DIT_API_RUN_CRUD_PROBE", "1")
    monkeypatch.setenv("DIT_API_CRUD_PROBE_SAFETY_REVIEWED", "1")
    monkeypatch.setattr(probe, "Settings", Mock(side_effect=ValueError("private-host password")))
    assert probe.main() == 2
    output = capsys.readouterr().out
    assert "private-host" not in output and "password" not in output


@pytest.fixture
def database(tmp_path, monkeypatch):
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'synthetic.sqlite'}", poolclass=NullPool
    )

    @event.listens_for(engine.sync_engine, "connect")
    def setup(connection, record):
        connection.isolation_level = None
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    @event.listens_for(engine.sync_engine, "begin")
    def begin(connection):
        # SQLite's offline transaction shim is equivalent to the DBAPI-level begin that the
        # real dialect manages; do not loosen the production SQL verb guard for this shim.
        cursor = connection.connection.cursor()
        try:
            cursor.execute("BEGIN")
        finally:
            cursor.close()

    async def initialize():
        # Only the isolated test creates SQLite tables. The probe has no schema creator.
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

    asyncio.run(initialize())
    monkeypatch.setattr(probe, "require_preconditions", AsyncMock())
    fixture = probe.Fixture()
    monkeypatch.setattr(probe, "Fixture", lambda: fixture)
    yield engine, fixture
    asyncio.run(engine.dispose())


def test_real_sqlite_adapters_rollback_no_commit_no_ddl_no_legacy_records(database):
    engine, fixture = database
    statements = []

    def guard(conn, cursor, sql, parameters, context, many):
        statements.append(sql)
        first = sql.strip().split()[0].upper()
        assert first not in {"CREATE", "ALTER", "DROP", "TRUNCATE", "GRANT", "COMMIT"}
        assert not any(
            f" {name} " in sql.casefold()
            for name in ("students", "auth_sessions", "enrollments", "question_logs")
        )

    def no_commit(connection):
        raise AssertionError("A physical commit is forbidden in the probe")

    event.listen(engine.sync_engine, "before_cursor_execute", guard)
    event.listen(engine.sync_engine, "commit", no_commit)
    try:
        report = asyncio.run(probe.run_probe(engine))
        assert report["status"] == "PASS"
        assert report["checks"]["anonymous_crud"] == "PASS"
        assert report["checks"]["recruitment_create_read_update_cancel"] == "PASS"
        assert report["checks"]["saved_opportunity_crud"] == "PASS"
        assert report["checks"]["nested_rollback"] == "PASS"
        assert report["fixture_absence_next_transaction"] == "VERIFIED"
        assert report["committed_fixture_rows"] == report["legacy_record_reads"] == 0
        assert "INSERT INTO identities" in "\n".join(statements)
        assert all(str(user) not in json.dumps(report) for user in fixture.actors)
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", guard)
        event.remove(engine.sync_engine, "commit", no_commit)


def test_failure_after_fixture_creation_still_rolls_back_and_checks_absence(database, monkeypatch):
    engine, fixture = database
    monkeypatch.setattr(
        probe, "exercise", Mock(side_effect=RuntimeError("private-password-and-record"))
    )
    report = asyncio.run(probe.run_probe(engine))
    assert report["status"] == "FAILED"
    assert report["outer_rollback"] == report["fixture_absence_next_transaction"] == "VERIFIED"
    assert "private-password" not in json.dumps(report)
    assert fixture.resources == set()


def test_cancelled_probe_also_rolls_back(database, monkeypatch):
    engine, fixture = database
    monkeypatch.setattr(probe, "exercise", Mock(side_effect=asyncio.CancelledError()))
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(probe.run_probe(engine))

    async def check():
        async with engine.connect() as connection:
            return await connection.run_sync(probe.fixtures_absent, fixture)

    assert asyncio.run(check())


@pytest.mark.parametrize("operation", ["ddl", "physical_commit"])
def test_runtime_guard_blocks_injected_adapter_side_effect_and_removes_only_own_listeners(
    database, monkeypatch, operation
):
    engine, fixture = database
    observed = []

    def external_listener(*args):
        observed.append(True)

    event.listen(engine.sync_engine, "before_cursor_execute", external_listener)

    def unsafe_adapter(session, fixture, now):
        if operation == "ddl":
            session.execute(text("CREATE TABLE accidental_probe_table (id INT)"))
        else:
            session.connection().commit()

    monkeypatch.setattr(probe, "exercise", unsafe_adapter)
    try:
        report = asyncio.run(probe.run_probe(engine))
        assert report["status"] == "FAILED"
        assert report["fixture_absence_next_transaction"] == "VERIFIED"
        assert report["committed_fixture_rows"] == 0
        assert event.contains(engine.sync_engine, "before_cursor_execute", external_listener)

        async def check():
            async with engine.connect() as connection:
                tables = await connection.run_sync(lambda conn: inspect(conn).get_table_names())
                # Our connection guard is gone; unrelated callers/listeners remain usable.
                await connection.execute(text("SELECT 1;"))
                return tables

        assert "accidental_probe_table" not in asyncio.run(check())
        assert observed
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", external_listener)


@pytest.mark.parametrize("dispose_fails", [False, True])
def test_cli_runner_sanitizes_connection_and_dispose_failure(monkeypatch, dispose_fails):
    engine = Mock(
        dispose=AsyncMock(side_effect=RuntimeError("private-password") if dispose_fails else None)
    )
    monkeypatch.setattr(probe, "create_database_engine", Mock(return_value=engine))
    monkeypatch.setattr(probe, "run_probe", AsyncMock(side_effect=RuntimeError("private-password")))
    result = asyncio.run(probe._run(object()))
    assert result == {"status": "FAILED_OR_BLOCKED", "cleanup": "NOT_VERIFIED"}
    engine.dispose.assert_awaited_once()


class Result:
    def __init__(self, value):
        self.value = value

    def one(self):
        return self.value

    def all(self):
        return self.value

    def scalar_one(self):
        return self.value


@pytest.mark.parametrize(
    "change",
    [
        "wrong_dialect",
        "wrong_version",
        "wrong_collation",
        "wrong_schema",
        "missing_columns",
        "myisam",
        "missing_engine",
        "visible_trigger",
    ],
)
def test_preconditions_fail_before_any_fixture_dml(monkeypatch, change):
    connection = Mock()
    connection.dialect.name = "sqlite" if change == "wrong_dialect" else "mysql"
    server = ["11.4.0-MariaDB", "utf8mb4_unicode_ci", "ditnow"]
    if change == "wrong_version":
        server[0] = "8.0-MySQL"
    elif change == "wrong_collation":
        server[1] = "other"
    elif change == "wrong_schema":
        server[2] = "other"
    engines = [
        (name, "MyISAM" if change == "myisam" else "InnoDB") for name in Base.metadata.tables
    ]
    if change == "missing_engine":
        engines.pop()
    connection.execute = AsyncMock(
        side_effect=[
            Result(tuple(server)),
            Result(engines),
            Result(1 if change == "visible_trigger" else 0),
        ]
    )
    connection.run_sync = AsyncMock(
        return_value={"column_names_ready": change != "missing_columns"}
    )
    with pytest.raises(probe.ProbeBlocked):
        asyncio.run(probe.require_preconditions(connection))
    assert all(str(call.args[0]).startswith("SELECT") for call in connection.execute.call_args_list)


def test_zero_visible_triggers_is_only_metadata_not_privileged_review():
    tree = ast.parse(Path(probe.__file__).read_text(encoding="utf-8"))
    calls = {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    # Domain services legitimately expose create(); actual DDL is also rejected by the
    # SQL execution/physical-commit guard in the real offline adapter scenario above.
    assert not calls & {"commit", "create_all", "drop_all", "drop"}
    fixture = probe.Fixture()
    assert {model.__tablename__ for model, _ in probe.fixture_predicates(fixture)} == set(
        Base.metadata.tables
    )
