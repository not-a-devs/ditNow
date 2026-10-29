"""Offline migration contracts only; no MariaDB, credentials, DDL on a real DB or network."""

import asyncio
import json
import re
import ssl
from copy import deepcopy
from pathlib import Path
from unittest.mock import AsyncMock, Mock

import pytest
from pydantic import ValidationError

from app.db import migration_runner as module
from app.db.migration_runner import (
    DDL_CHECKSUM,
    LEGACY,
    VERSION,
    Manifest,
    MigrationBlocked,
    MigrationCredentials,
    connect_migrator,
    main,
    plan,
    run_migration,
)


class FakeConnection:
    """Metadata/implicit-commit simulator, not an implementation of MariaDB locking."""

    endpoint_checksum = "1" * 64

    def __init__(self, tables=None):
        self.tables = (
            tables
            if tables is not None
            else {name: f"CREATE TABLE {name} (legacy INTEGER)" for name in LEGACY}
        )
        self.queries = []
        self.created = []
        self.closed = False
        self.locked = False
        self.lock_result = 1
        self.server = [
            "ditnow",
            "ditnow_migrator@private.invalid",
            "11.4.10-MariaDB",
            "utf8mb4_unicode_ci",
            1,
            1,
            "STRICT_TRANS_TABLES",
        ]
        self.fail_before = None
        self.fail_after = None
        self.mutate_legacy = False

    async def query(self, sql, parameters=()):
        self.queries.append((sql, parameters))
        if sql.startswith("SELECT GET_LOCK"):
            self.locked = self.lock_result == 1
            return [(self.lock_result,)]
        if sql.startswith("SELECT RELEASE_LOCK"):
            self.locked = False
            return [(1,)]
        if sql.startswith("SELECT IS_USED_LOCK"):
            return [(int(self.locked),)]
        if sql.startswith("SELECT DATABASE"):
            return [tuple(self.server)]
        if sql.startswith("SHOW FULL TABLES"):
            return [(name, "BASE TABLE") for name in self.tables]
        if sql.startswith("SHOW CREATE TABLE"):
            table = sql.split("`ditnow`.`")[1].removesuffix("`")
            return [(table, self.tables[table])]
        match = re.match(r"CREATE TABLE ([a-z_]+) \(", sql)
        assert match and self.locked, "Only the reviewed CREATE while holding a lock is allowed"
        table = match[1]
        assert table not in self.tables
        if len(self.created) == self.fail_before:
            raise RuntimeError("private-host private-password")
        self.tables[table] = sql  # Simulate DDL committed before a transport failure.
        self.created.append(table)
        if self.mutate_legacy:
            self.tables["students"] += " CHANGED"
        if len(self.created) == self.fail_after:
            raise RuntimeError("private-host private-password")
        return []

    def close(self):
        self.closed = True


def run(connection, path, **options):
    return asyncio.run(run_migration(connection, path, DDL_CHECKSUM, **options))


def assert_blocked(code, call):
    with pytest.raises(MigrationBlocked) as error:
        call()
    assert str(error.value) == code


def test_reviewed_plan_has_only_16_new_create_tables_and_pinned_normalized_checksum():
    statements = plan()
    assert len(statements) == 16 and len({table for table, _ in statements}) == 16
    assert not {table for table, _ in statements} & LEGACY
    assert all(sql.startswith("CREATE TABLE ") and ";" not in sql for _, sql in statements)
    assert VERSION == "p0-initial-v1"


def test_default_cli_never_reads_credentials_connects_or_writes_manifest(monkeypatch, capsys):
    credentials = Mock(side_effect=AssertionError("must not read environment credentials"))
    connection = AsyncMock(side_effect=AssertionError("must not connect"))
    monkeypatch.setattr(module, "MigrationCredentials", credentials)
    monkeypatch.setattr(module, "connect_migrator", connection)
    assert main([]) == 0
    assert json.loads(capsys.readouterr().out) == {
        "mode": "DRY_RUN",
        "connection": "NOT_RUN",
        "version": VERSION,
        "ddl_checksum": DDL_CHECKSUM,
        "statements": 16,
        "persistent_writes": 0,
    }
    credentials.assert_not_called()
    connection.assert_not_called()


@pytest.mark.parametrize("args", [["--apply"], ["--inspect"], ["--resume"]])
def test_live_cli_requires_explicit_target_checksum_and_manifest(monkeypatch, capsys, args):
    credentials = Mock(side_effect=AssertionError("must not read credentials"))
    monkeypatch.setattr(module, "MigrationCredentials", credentials)
    assert main(args) == 2
    assert json.loads(capsys.readouterr().out)["status"] == "BLOCKED"
    credentials.assert_not_called()


def test_inspection_is_read_only_and_does_not_publish_progress(tmp_path):
    connection = FakeConnection()
    path = tmp_path / "state.json"
    report = run(connection, path)
    assert report == {"mode": "INSPECT", "ready": True, "remaining": 16, "persistent_writes": 0}
    assert not path.exists() and not connection.created
    assert connection.closed and not connection.locked


def test_apply_records_each_definition_and_preserves_legacy_and_existing_ddl(tmp_path):
    connection = FakeConnection()
    legacy = deepcopy(connection.tables)
    path = tmp_path / "state.json"
    report = run(connection, path, apply=True)
    assert report["complete"] and report["rollback"] == "NOT_AVAILABLE"
    manifest = Manifest.model_validate_json(path.read_text())
    assert len(connection.created) == 16 and all(step.state == "APPLIED" for step in manifest.steps)
    assert all(connection.tables[name] == value for name, value in legacy.items())
    assert len(connection.tables) == 25 and connection.closed and not connection.locked
    assert not any(
        sql.startswith(("DROP", "ALTER", "INSERT", "GRANT", "DELETE"))
        for sql, _ in connection.queries
    )
    assert "private.invalid" not in path.read_text()
    assert not path.with_name("state.json.migration-lock").exists()


@pytest.mark.parametrize(
    "index,value,code",
    [
        (0, "ditnow_chatbot", "WRONG_DATABASE_OR_MIGRATOR"),
        (1, "ditnow_app@private.invalid", "WRONG_DATABASE_OR_MIGRATOR"),
        (2, "11.8.0-MariaDB", "SERVER_VERSION_UNAPPROVED"),
        (3, "utf8mb4_uca1400_ai_ci", "CONNECTION_CONSTRAINT_SETTINGS_INVALID"),
        (4, 0, "CONNECTION_CONSTRAINT_SETTINGS_INVALID"),
        (5, 0, "CONNECTION_CONSTRAINT_SETTINGS_INVALID"),
        (6, "", "CONNECTION_CONSTRAINT_SETTINGS_INVALID"),
    ],
)
def test_preflight_fails_before_any_ddl(tmp_path, index, value, code):
    connection = FakeConnection()
    connection.server[index] = value
    assert_blocked(code, lambda: run(connection, tmp_path / "state.json", apply=True))
    assert not connection.created and connection.closed and not connection.locked


def test_lock_timeout_missing_legacy_and_target_collision_never_blindly_apply(tmp_path):
    for mode, code in [
        ("lock", "MIGRATION_LOCK_UNAVAILABLE"),
        ("missing", "LEGACY_BASELINE_MISSING"),
        ("collision", "UNRECORDED_OR_UNCERTAIN_TARGET"),
        ("extra", "UNEXPECTED_EXISTING_TARGET"),
    ]:
        connection = FakeConnection()
        if mode == "lock":
            connection.lock_result = 0
        elif mode == "missing":
            del connection.tables["students"]
        elif mode == "collision":
            connection.tables[plan()[0][0]] = "unapproved existing definition"
        else:
            connection.tables["another_team_table"] = "preserved"
        assert_blocked(
            code, lambda connection=connection: run(connection, tmp_path / "state.json", apply=True)
        )
        assert not connection.created and connection.closed


def test_recorded_partial_apply_requires_explicit_resume_and_definition_identity(tmp_path):
    path = tmp_path / "state.json"
    first = FakeConnection()
    first.fail_before = 2
    assert_blocked("MIGRATION_STOPPED_REVIEW_MANIFEST", lambda: run(first, path, apply=True))
    manifest = Manifest.model_validate_json(path.read_text())
    assert [s.state for s in manifest.steps[:3]] == ["APPLIED", "APPLIED", "PENDING"]
    second = FakeConnection(first.tables)
    assert_blocked("EXPLICIT_RESUME_REQUIRED", lambda: run(second, path, apply=True))
    third = FakeConnection(first.tables)
    report = run(third, path, apply=True, resume=True)
    assert report["applied_statements"] == 16 and len(third.created) == 14
    assert all(s.state == "APPLIED" for s in Manifest.model_validate_json(path.read_text()).steps)


def test_transport_failure_after_ddl_is_uncertain_and_never_automatically_adopted(tmp_path):
    path = tmp_path / "state.json"
    first = FakeConnection()
    first.fail_after = 3
    assert_blocked("MIGRATION_STOPPED_REVIEW_MANIFEST", lambda: run(first, path, apply=True))
    third_table = plan()[2][0]
    assert third_table in first.tables
    second = FakeConnection(first.tables)
    assert_blocked(
        "UNRECORDED_OR_UNCERTAIN_TARGET", lambda: run(second, path, apply=True, resume=True)
    )
    assert not second.created and third_table in second.tables


@pytest.mark.parametrize("changed", ["legacy", "applied", "endpoint", "checksum"])
def test_resume_rejects_changed_definitions_endpoint_or_version_checksum(tmp_path, changed):
    path = tmp_path / "state.json"
    first = FakeConnection()
    first.fail_before = 2
    with pytest.raises(MigrationBlocked):
        run(first, path, apply=True)
    second = FakeConnection(deepcopy(first.tables))
    if changed == "legacy":
        second.tables["students"] += " changed"
    elif changed == "applied":
        second.tables[plan()[0][0]] += " changed"
    elif changed == "endpoint":
        second.endpoint_checksum = "2" * 64
    else:
        data = json.loads(path.read_text())
        data["ddl_checksum"] = "3" * 64
        path.write_text(json.dumps(data))
    code = "APPLIED_DEFINITION_MISMATCH" if changed == "applied" else "MANIFEST_BASELINE_MISMATCH"
    assert_blocked(code, lambda: run(second, path, apply=True, resume=True))
    assert not second.created


def test_legacy_change_during_create_stops_with_pending_manifest_no_drop(tmp_path):
    connection = FakeConnection()
    connection.mutate_legacy = True
    path = tmp_path / "state.json"
    assert_blocked("LEGACY_DEFINITION_CHANGED", lambda: run(connection, path, apply=True))
    assert len(connection.created) == 1 and connection.created[0] in connection.tables
    assert Manifest.model_validate_json(path.read_text()).steps[0].state == "PENDING"


def test_manifest_write_failure_before_ddl_and_after_ddl_fail_closed(tmp_path, monkeypatch):
    actual = module.write_manifest
    for fail_at in [1, 3]:
        path = tmp_path / f"failure-{fail_at}.json"
        connection = FakeConnection()
        calls = 0

        def fail_write(path, manifest, fail_at=fail_at):
            nonlocal calls
            calls += 1
            if calls == fail_at:
                raise OSError("private-path private-password")
            actual(path, manifest)

        monkeypatch.setattr(module, "write_manifest", fail_write)
        assert_blocked(
            "MIGRATION_STOPPED_REVIEW_MANIFEST",
            lambda connection=connection, path=path: run(connection, path, apply=True),
        )
        assert len(connection.created) == (0 if fail_at == 1 else 1)
        assert connection.closed
        if fail_at == 3:
            monkeypatch.setattr(module, "write_manifest", actual)
            assert_blocked(
                "UNRECORDED_OR_UNCERTAIN_TARGET",
                lambda connection=connection, path=path: run(
                    FakeConnection(connection.tables), path, apply=True, resume=True
                ),
            )


def test_manifest_requires_outside_repo_absolute_operator_directory(tmp_path):
    for path in [Path("relative.json"), Path(__file__).resolve().parent / "not-written.json"]:
        connection = FakeConnection()
        assert_blocked(
            "OUTSIDE_REPOSITORY_MANIFEST_REQUIRED",
            lambda connection=connection, path=path: run(connection, path, apply=True),
        )
        assert not connection.queries and connection.closed
    path = tmp_path / "state.json"
    lock = tmp_path / "state.json.migration-lock"
    lock.write_text("another process")
    connection = FakeConnection()
    assert_blocked("EXCLUSIVE_MANIFEST_LOCK_REQUIRED", lambda: run(connection, path, apply=True))
    assert lock.read_text() == "another process" and not connection.queries


def credentials(tmp_path, **changes):
    ca = tmp_path / "ca.pem"
    ca.write_text("fictional-ca-fixture")
    values = {
        "host": "migration.private.invalid",
        "database": "ditnow",
        "user": "ditnow_migrator",
        "password": "fictional-migration-secret",
        "tls_ca_file": ca,
    }
    return MigrationCredentials(**(values | changes))


def test_migrator_credentials_are_separate_and_not_serialized(tmp_path):
    settings = credentials(tmp_path)
    assert settings.user == "ditnow_migrator" and settings.database == "ditnow"
    for secret in [settings.host, "fictional-migration-secret", str(settings.tls_ca_file)]:
        assert secret not in repr(settings) + settings.model_dump_json()
    for changes in [
        {"user": "ditnow_app"},
        {"user": "root"},
        {"database": "ditnow_chatbot"},
        {"password": ""},
        {"host": "mysql://credential@host"},
    ]:
        with pytest.raises(ValidationError):
            credentials(tmp_path, **changes)


@pytest.mark.parametrize("fails", [False, True])
def test_migrator_connection_preserves_reviewed_tls_and_sanitizes_errors(
    tmp_path, monkeypatch, fails
):
    settings = credentials(tmp_path)
    context = ssl.create_default_context()
    monkeypatch.setattr(module.ssl, "create_default_context", lambda **kwargs: context)
    raw = Mock()
    raw._connect = AsyncMock(
        side_effect=RuntimeError("private-host private-password") if fails else None
    )
    factory = Mock(return_value=raw)
    monkeypatch.setattr(module, "TLSRequiredConnection", factory)
    if fails:
        assert_blocked(
            "MIGRATION_CONNECTION_FAILED", lambda: asyncio.run(connect_migrator(settings))
        )
        raw.close.assert_called_once()
    else:
        result = asyncio.run(connect_migrator(settings))
        result.close()
    kwargs = factory.call_args.kwargs
    assert kwargs["ssl"].verify_mode == ssl.CERT_REQUIRED and kwargs["ssl"].check_hostname
    assert kwargs["user"] == "ditnow_migrator" and kwargs["db"] == "ditnow"
    assert kwargs["init_command"] == module.SESSION_CHARSET_SQL
    assert kwargs["local_infile"] is kwargs["echo"] is kwargs["autocommit"] is False


def test_live_cli_sanitizes_raw_failure(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(
        module, "_live", AsyncMock(side_effect=RuntimeError("private-host private-password"))
    )
    args = [
        "--apply",
        "--confirm-database",
        "ditnow",
        "--expected-checksum",
        DDL_CHECKSUM,
        "--manifest",
        str(tmp_path / "state.json"),
    ]
    assert main(args) == 2
    output = capsys.readouterr().out
    assert "private-host" not in output and "private-password" not in output
    assert json.loads(output)["rollback"] == "NOT_CLAIMED"


def test_rejected_cli_secret_argument_is_not_echoed(capsys):
    assert main(["--password", "fictional-private-password"]) == 2
    captured = capsys.readouterr()
    assert "fictional-private-password" not in captured.out + captured.err
    assert json.loads(captured.out)["code"] == "ARGUMENTS_INVALID"


def test_leftover_pending_file_requires_manual_recovery_before_any_db_query(tmp_path):
    path = tmp_path / "state.json"
    path.with_name("state.json.pending-write").write_text("unpublished progress")
    connection = FakeConnection()
    assert_blocked("MANIFEST_RECOVERY_REQUIRED", lambda: run(connection, path, apply=True))
    assert connection.closed and not connection.queries and not connection.created
