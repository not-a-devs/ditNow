"""TASK-DEMO-ACCOUNT-OPS offline SQLite checks. Not MariaDB, GRANT, TLS or real-DB proof."""

import asyncio
import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, Mock
from uuid import UUID

import pytest
from chatbot.app.auth import verify_password
from chatbot.app.models import StudentRow
from pydantic import SecretStr
from sqlalchemy import event, func, select, text
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine
from sqlalchemy.pool import NullPool

from app.db.models import (
    AcademicMembershipRow,
    AuditLogRow,
    Base,
    DepartmentRow,
    IdentityRow,
    OpportunityRow,
    ProfileRow,
    RoleAssignmentRow,
)
from app.operations import demo_accounts as ops

PASSWORD_A = "synthetic-pass-A-91x"
PASSWORD_B = "synthetic-pass-B-27q"
NOW = datetime(2026, 10, 30, 9, 0, tzinfo=UTC)
APPROVAL = "ROOT-APPROVAL-TEST-001"
MODELS = (
    IdentityRow,
    ProfileRow,
    DepartmentRow,
    AcademicMembershipRow,
    RoleAssignmentRow,
    AuditLogRow,
    OpportunityRow,
    StudentRow,
)


def passwords(a=PASSWORD_A, b=PASSWORD_B):
    return ops.DemoAccountPasswords(password_a=SecretStr(a), password_b=SecretStr(b))


async def offline_readiness(connection):
    """SQLite has no MariaDB metadata; the real readiness is covered separately below."""


@pytest.fixture
def engine(tmp_path):
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'demo.sqlite'}", poolclass=NullPool, hide_parameters=True
    )

    @event.listens_for(engine.sync_engine, "connect")
    def setup(connection, record):
        connection.isolation_level = None
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    @event.listens_for(engine.sync_engine, "begin")
    def begin(connection):
        # SQLite transaction shim at the DBAPI level; the production verb guard is unchanged.
        cursor = connection.connection.cursor()
        try:
            cursor.execute("BEGIN")
        finally:
            cursor.close()

    async def initialize():
        # Only this isolated test creates schema. The operator module has no schema creator.
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
            await connection.run_sync(StudentRow.__table__.create)

    asyncio.run(initialize())
    yield engine
    asyncio.run(engine.dispose())


def run(engine, *, secrets=None, **kwargs):
    return asyncio.run(
        ops.provision(
            engine,
            secrets or passwords(),
            APPROVAL,
            readiness=offline_readiness,
            clock=lambda: NOW,
            **kwargs,
        )
    )


def query(engine, fn):
    async def go():
        async with engine.connect() as connection:
            return await connection.run_sync(fn)

    return asyncio.run(go())


def counts(engine):
    return query(
        engine,
        lambda conn: {
            model.__tablename__: conn.scalar(select(func.count()).select_from(model))
            for model in MODELS
        },
    )


def insert_existing(engine, *rows):
    async def go():
        async with engine.begin() as connection:
            for statement in rows:
                await connection.execute(statement)

    asyncio.run(go())


def test_success_creates_exact_synthetic_ledger_with_single_commit(engine, caplog):
    statements, commits = [], []
    event.listen(
        engine.sync_engine,
        "before_cursor_execute",
        lambda conn, cursor, sql, *args: statements.append(sql),
    )
    event.listen(engine.sync_engine, "commit", lambda conn: commits.append(True))
    # INFO includes SQLAlchemy statement logs; the engine hides parameters like the strict
    # runtime factory. Test-only aiosqlite DEBUG tracing is not an application log channel.
    caplog.set_level(logging.INFO)

    report = run(engine)

    assert report["status"] == "APPLIED" and report["commits"] == 1 and len(commits) == 1
    assert report["post_commit_verification"] == "MATCHED"
    assert report["rows_created"] == ops.PLANNED_ROWS
    assert counts(engine) == {
        "identities": 3,
        "profiles": 2,
        "departments": 2,
        "academic_memberships": 2,
        "role_assignments": 2,
        "audit_logs": 2,
        "opportunities": 1,
        "students": 2,
    }
    verbs = {sql.lstrip().split(None, 1)[0].upper() for sql in statements}
    assert verbs <= {"SELECT", "INSERT"}, verbs

    def snapshot(conn):
        return {
            "identities": conn.execute(select(IdentityRow)).all(),
            "profiles": conn.execute(select(ProfileRow)).all(),
            "departments": conn.execute(select(DepartmentRow)).all(),
            "memberships": conn.execute(select(AcademicMembershipRow)).all(),
            "roles": conn.execute(select(RoleAssignmentRow)).all(),
            "audits": conn.execute(select(AuditLogRow)).all(),
            "opportunities": conn.execute(select(OpportunityRow)).all(),
            "students": conn.execute(select(StudentRow)).all(),
        }

    data = query(engine, snapshot)
    accounts = {item["student_id"]: item for item in report["accounts"]}
    operator = UUID(report["operator_identity_id"])
    identities = {row.id: row for row in data["identities"]}
    assert identities[operator].status == "disabled"
    assert identities[operator].source_kind == "DEMO"
    assert identities[operator].issuer != ops.STUDENT_ISSUER
    departments = {row.id: row for row in data["departments"]}
    assert {row.code for row in data["departments"]} == {"DEMO-A", "DEMO-B"}
    students = {row.student_id: row for row in data["students"]}
    hashes = []
    for student_id, display, code, password in (
        ("DITDEMO_A", "[가상]학생A", "DEMO-A", PASSWORD_A),
        ("DITDEMO_B", "[가상]학생B", "DEMO-B", PASSWORD_B),
    ):
        item = accounts[student_id]
        user, department = UUID(item["identity_id"]), UUID(item["department_id"])
        identity = identities[user]
        assert (identity.issuer, identity.subject) == (ops.STUDENT_ISSUER, student_id)
        assert (identity.status, identity.source_kind) == ("active", "DEMO")
        assert departments[department].code == code == item["department_code"]
        assert departments[department].source_kind == "DEMO"
        profile = [row for row in data["profiles"] if row.user_id == user]
        assert [(row.display_name, row.source_kind) for row in profile] == [(display, "DEMO")]
        memberships = [row for row in data["memberships"] if row.user_id == user]
        assert [(m.department_id, m.academic_year, m.status, m.valid_to) for m in memberships] == [
            (department, 1, "active", None)
        ]
        assert memberships[0].valid_from == NOW
        roles = [row for row in data["roles"] if row.user_id == user]
        assert [(r.role, r.scope_type, r.scope_id, r.status) for r in roles] == [
            ("student", "department", department, "active")
        ]
        audits = [row for row in data["audits"] if row.entity_id == user]
        assert [(a.event, a.resource_kind, a.actor_id, a.source_kind, a.id) for a in audits] == [
            (
                "identity_binding_approved",
                "identity_binding",
                operator,
                "DEMO",
                UUID(item["audit_log_id"]),
            )
        ]
        legacy = students[student_id]
        # Legacy required initial fields match; canonical rows are the sole authority afterward.
        assert (legacy.name, legacy.dept_id, legacy.grade, legacy.kakao_id) == (
            display,
            code,
            1,
            None,
        )
        assert verify_password(password, legacy.password_hash)
        hashes.append(legacy.password_hash)
    # Operator: audit actor only, never a login, profile, membership or role holder.
    assert operator not in {row.user_id for row in data["profiles"]}
    assert operator not in {row.user_id for row in data["memberships"]}
    assert operator not in {row.user_id for row in data["roles"]}
    assert all(row.role == "student" for row in data["roles"])
    assert ops.OPERATOR_SUBJECT not in students
    [opportunity] = data["opportunities"]
    assert opportunity.id == UUID(report["opportunity_id"])
    assert (opportunity.title, opportunity.status, opportunity.submission_mode) == (
        ops.OPPORTUNITY_TITLE,
        "published",
        "info_only",
    )
    assert opportunity.kind == "contest" and opportunity.source_kind == "DEMO"
    assert opportunity.source_url is None and opportunity.checked_at is None
    assert opportunity.original_url is None and opportunity.organization == ""
    assert report["opportunity_marker"] == ops.OPPORTUNITY_MARKER
    assert ops.OPPORTUNITY_MARKER in opportunity.title
    assert sorted(report["audit_log_ids"]) == sorted(str(a.id) for a in data["audits"])
    # No password, hash or DSN in output or logs.
    output = json.dumps(report, ensure_ascii=False) + caplog.text
    for secret in (PASSWORD_A, PASSWORD_B, "pbkdf2", "sqlite", *hashes):
        assert secret not in output
    assert report["secret_material"] == "NOT_OUTPUT"
    assert report["runtime_audit_allowlist"] == "OPERATOR_REVIEW_REQUIRED"


@pytest.mark.parametrize(
    ("statement", "code"),
    [
        (
            text(
                "INSERT INTO students (student_id, name, dept_id, grade, password_hash) "
                "VALUES ('DITDEMO_A', 'existing', 'X', 2, 'preexisting-hash')"
            ),
            "SYNTHETIC_STUDENT_ID_EXISTS",
        ),
        (
            DepartmentRow.__table__.insert().values(
                id=UUID(int=7),
                code="DEMO-B",
                name="existing",
                revision=1,
                source_kind="DEMO",
                created_at=NOW,
                updated_at=NOW,
            ),
            "SYNTHETIC_DEPARTMENT_CODE_EXISTS",
        ),
    ],
)
def test_collision_fails_closed_without_adopt_overwrite_or_password_reset(engine, statement, code):
    insert_existing(engine, statement)
    before = counts(engine)
    with pytest.raises(ops.DemoAccountBlocked) as error:
        run(engine)
    assert code in str(error.value) and str(error.value).startswith("COLLISION:")
    assert counts(engine) == before
    legacy = query(engine, lambda c: c.execute(select(StudentRow)).all())
    assert all(row.password_hash == "preexisting-hash" for row in legacy)


@pytest.mark.parametrize(
    ("issuer", "subject"),
    [(ops.STUDENT_ISSUER, "DITDEMO_B"), (ops.OPERATOR_ISSUER, ops.OPERATOR_SUBJECT)],
)
def test_existing_issuer_subject_collision_is_rejected(engine, issuer, subject):
    async def existing():
        async with engine.begin() as connection:
            await connection.run_sync(
                lambda conn: conn.execute(
                    IdentityRow.__table__.insert(),
                    [
                        {
                            "id": UUID(int=9),
                            "issuer": issuer,
                            "subject": subject,
                            "binding_digest": ops.subject_digest(issuer, subject),
                            "status": "pending",
                            "revision": 1,
                            "source_kind": "DEMO",
                            "created_at": NOW,
                            "updated_at": NOW,
                        }
                    ],
                )
            )

    asyncio.run(existing())
    with pytest.raises(ops.DemoAccountBlocked, match="SYNTHETIC_ISSUER_SUBJECT_EXISTS"):
        run(engine)
    assert counts(engine)["identities"] == 1 and counts(engine)["students"] == 0


def test_mid_transaction_failure_rolls_back_every_row(engine, monkeypatch):
    original = ops.insert_rows

    def partial(session, plan, hashes, now):
        original(session, plan, hashes, now)
        raise RuntimeError("private-password-hash-detail")

    monkeypatch.setattr(ops, "insert_rows", partial)
    with pytest.raises(RuntimeError):
        run(engine)
    assert set(counts(engine).values()) == {0}


def test_constraint_violation_rolls_back_atomically(engine, monkeypatch):
    def bad_hashes(password, salt=None):
        return None  # NOT NULL password_hash: the legacy insert fails after canonical rows

    monkeypatch.setattr(ops, "hash_password", bad_hashes)
    with pytest.raises(Exception):  # noqa: B017 - any DB error must abort the whole UOW
        run(engine)
    assert set(counts(engine).values()) == {0}


@pytest.mark.parametrize("operation", ["ddl", "update", "early_commit"])
def test_guard_blocks_ddl_updates_and_unarmed_commit(engine, monkeypatch, operation):
    def unsafe(session, plan, hashes, now):
        if operation == "ddl":
            session.execute(text("CREATE TABLE accidental_demo (id INT)"))
        elif operation == "update":
            session.execute(text("UPDATE students SET grade = 2"))
        else:
            session.connection().commit()

    monkeypatch.setattr(ops, "insert_rows", unsafe)
    with pytest.raises(ops.DemoAccountBlocked):
        run(engine)
    assert set(counts(engine).values()) == {0}
    tables = query(engine, lambda c: c.exec_driver_sql("SELECT name FROM sqlite_master").all())
    assert "accidental_demo" not in {row[0] for row in tables}


def test_second_apply_is_rejected_not_adopted(engine):
    first = run(engine)
    with pytest.raises(ops.DemoAccountBlocked, match="COLLISION"):
        run(engine, secrets=passwords("another-pass-A-55z", "another-pass-B-66y"))
    assert counts(engine)["students"] == 2
    legacy = query(engine, lambda c: c.execute(select(StudentRow)).all())
    assert all(not verify_password("another-pass-A-55z", row.password_hash) for row in legacy)
    assert first["status"] == "APPLIED"


def test_default_readiness_rejects_non_mariadb_without_writes(engine):
    with pytest.raises(ops.DemoAccountBlocked, match="MARIADB_REQUIRED"):
        asyncio.run(ops.provision(engine, passwords(), APPROVAL))
    assert set(counts(engine).values()) == {0}


def test_readiness_contract_is_25_tables_including_legacy_students():
    assert len(ops.REQUIRED_TABLES) == 25
    assert {"students", "auth_sessions", "identities", "audit_logs"} <= set(ops.REQUIRED_TABLES)


@pytest.mark.parametrize("reference", ["", "x", "has space", "a;drop", "ok" + "x" * 80])
def test_provision_requires_valid_approval_reference(engine, reference):
    with pytest.raises(ops.DemoAccountBlocked, match="APPROVAL_REFERENCE_REQUIRED"):
        asyncio.run(ops.provision(engine, passwords(), reference, readiness=offline_readiness))


@pytest.fixture
def forbid_live(monkeypatch):
    for name in ops.PASSWORD_ENV:
        monkeypatch.delenv(name, raising=False)
    settings = Mock(side_effect=AssertionError("settings forbidden"))
    factory = Mock(side_effect=AssertionError("network forbidden"))
    monkeypatch.setattr(ops, "Settings", settings)
    monkeypatch.setattr(ops, "create_database_engine", factory)
    return settings, factory


def test_default_cli_is_offline_dry_run(forbid_live, capsys):
    settings, factory = forbid_live
    assert ops.main([]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["mode"] == "DRY_RUN" and report["persistent_writes"] == 0
    assert report["connection"] == "NOT_RUN" and report["passwords"] == "NOT_READ"
    assert report["student_ids"] == ["DITDEMO_A", "DITDEMO_B"]
    assert set(ops.PASSWORD_ENV) <= set(report["apply_requires"])
    settings.assert_not_called()
    factory.assert_not_called()


@pytest.mark.parametrize(
    ("argv", "code"),
    [
        (["--confirm-synthetic-only"], "APPLY_REQUIRED_FOR_OPTIONS"),
        (["--apply"], "SYNTHETIC_ONLY_CONFIRMATION_REQUIRED"),
        (["--apply", "--confirm-synthetic-only"], "APPROVAL_REFERENCE_REQUIRED"),
        (
            ["--apply", "--confirm-synthetic-only", "--approval-reference", APPROVAL],
            "INJECTED_PASSWORDS_REQUIRED",
        ),
        (["--apply", "--password", PASSWORD_A], "ARGUMENTS_INVALID"),
    ],
)
def test_cli_gates_before_settings_or_network(forbid_live, capsys, argv, code):
    settings, factory = forbid_live
    assert ops.main(argv) == 2
    output = capsys.readouterr()
    report = json.loads(output.out)
    assert report == {"status": "BLOCKED", "code": code, "persistent_writes": 0}
    assert PASSWORD_A not in output.out + output.err
    settings.assert_not_called()
    factory.assert_not_called()


@pytest.mark.parametrize(
    ("a", "b"),
    [
        (PASSWORD_A, PASSWORD_A),
        ("short", PASSWORD_B),
        (" " + PASSWORD_A, PASSWORD_B),
        ("ditdemo_a-long-pass", PASSWORD_B),
        ("x" * 65, PASSWORD_B),
    ],
)
def test_weak_or_reused_injected_passwords_are_rejected_without_echo(
    forbid_live, monkeypatch, capsys, a, b
):
    monkeypatch.setenv(ops.PASSWORD_ENV[0], a)
    monkeypatch.setenv(ops.PASSWORD_ENV[1], b)
    argv = ["--apply", "--confirm-synthetic-only", "--approval-reference", APPROVAL]
    assert ops.main(argv) == 2
    out = capsys.readouterr().out
    assert json.loads(out)["code"] == "INJECTED_PASSWORDS_REQUIRED"
    assert a not in out and b not in out
    forbid_live[0].assert_not_called()


def test_password_settings_have_no_defaults_or_repr():
    fields = ops.DemoAccountPasswords.model_fields
    assert all(fields[name].is_required() for name in ("password_a", "password_b"))
    assert PASSWORD_A not in repr(passwords()) and PASSWORD_A not in str(passwords().model_dump())


def test_apply_uses_strict_runtime_factory_and_sanitizes_failures(monkeypatch, capsys):
    monkeypatch.setenv(ops.PASSWORD_ENV[0], PASSWORD_A)
    monkeypatch.setenv(ops.PASSWORD_ENV[1], PASSWORD_B)
    settings = Mock(database_configured=True, db_user="ditnow_app")
    monkeypatch.setattr(ops, "Settings", Mock(return_value=settings))
    engine = Mock(dispose=AsyncMock(side_effect=RuntimeError("dsn-secret")))
    factory = Mock(return_value=engine)
    monkeypatch.setattr(ops, "create_database_engine", factory)
    monkeypatch.setattr(ops, "provision", AsyncMock(side_effect=RuntimeError("dsn-secret")))
    argv = ["--apply", "--confirm-synthetic-only", "--approval-reference", APPROVAL]
    assert ops.main(argv) == 2
    out = capsys.readouterr().out
    assert json.loads(out) == {
        "status": "BLOCKED",
        "code": "FAILED_BEFORE_COMMIT",
        "committed": "NO",
    }
    assert "dsn-secret" not in out and PASSWORD_A not in out
    factory.assert_called_once_with(settings)
    engine.dispose.assert_awaited_once()


def test_unconfigured_database_never_constructs_engine(monkeypatch, capsys):
    monkeypatch.setenv(ops.PASSWORD_ENV[0], PASSWORD_A)
    monkeypatch.setenv(ops.PASSWORD_ENV[1], PASSWORD_B)
    monkeypatch.setattr(ops, "Settings", Mock(return_value=Mock(database_configured=False)))
    factory = Mock(side_effect=AssertionError("network forbidden"))
    monkeypatch.setattr(ops, "create_database_engine", factory)
    argv = ["--apply", "--confirm-synthetic-only", "--approval-reference", APPROVAL]
    assert ops.main(argv) == 2
    assert json.loads(capsys.readouterr().out)["code"] == "DATABASE_NOT_CONFIGURED"
    factory.assert_not_called()


def test_commit_failure_is_reported_unknown_not_rolled_back(engine, monkeypatch):
    def fail_commit(conn):
        raise RuntimeError("network-detail")

    event.listen(engine.sync_engine, "commit", fail_commit)
    try:
        with pytest.raises(ops.DemoAccountBlocked, match="COMMIT_OUTCOME_UNKNOWN"):
            run(engine)
    finally:
        event.remove(engine.sync_engine, "commit", fail_commit)


def test_operator_module_is_never_wired_into_app_or_startup():
    root = Path(ops.__file__).resolve().parents[1]
    for path in root.rglob("*.py"):
        if path.parent.name != "operations":
            assert "app.operations" not in path.read_text(encoding="utf-8"), path
    source = Path(ops.__file__).read_text(encoding="utf-8")
    for forbidden in (".create_all(", ".drop_all(", '"DROP', '"GRANT', '"TRUNCATE', '"admin"'):
        assert forbidden not in source


def test_post_commit_connection_exit_failure_reports_yes_with_own_ids(engine, monkeypatch):
    original_provision = ops.provision
    original_exit = AsyncConnection.__aexit__

    async def isolated_provision(engine, secrets, approval, *, outcome):
        return await original_provision(
            engine,
            secrets,
            approval,
            readiness=offline_readiness,
            clock=lambda: NOW,
            outcome=outcome,
        )

    async def fail_release(connection, *args):
        await original_exit(connection, *args)
        raise RuntimeError("synthetic-password-or-dsn-must-not-be-printed")

    monkeypatch.setattr(ops, "provision", isolated_provision)
    monkeypatch.setattr(
        ops,
        "Settings",
        Mock(
            return_value=Mock(
                database_configured=True,
                db_user="ditnow_app",
            )
        ),
    )
    monkeypatch.setattr(ops, "create_database_engine", Mock(return_value=engine))
    with monkeypatch.context() as patch:
        patch.setattr(AsyncConnection, "__aexit__", fail_release)
        report = asyncio.run(ops._run(passwords(), APPROVAL))
    assert report["status"] == "BLOCKED" and report["committed"] == "YES"
    assert report["code"] == "POST_COMMIT_FAILURE_REVIEW_REQUIRED"
    assert len(report["accounts"]) == 2 and len(report["audit_log_ids"]) == 2
    assert counts(engine)["students"] == 2
    assert "synthetic-password-or-dsn" not in json.dumps(report)
    assert PASSWORD_A not in json.dumps(report) and PASSWORD_B not in json.dumps(report)


def test_commit_attempt_failure_reports_unknown_with_own_ids(engine, monkeypatch):
    original_provision = ops.provision

    async def isolated_provision(engine, secrets, approval, *, outcome):
        return await original_provision(
            engine,
            secrets,
            approval,
            readiness=offline_readiness,
            clock=lambda: NOW,
            outcome=outcome,
        )

    def fail_commit(connection):
        raise RuntimeError("synthetic-private-driver-error")

    monkeypatch.setattr(ops, "provision", isolated_provision)
    monkeypatch.setattr(
        ops,
        "Settings",
        Mock(
            return_value=Mock(
                database_configured=True,
                db_user="ditnow_app",
            )
        ),
    )
    monkeypatch.setattr(ops, "create_database_engine", Mock(return_value=engine))
    event.listen(engine.sync_engine, "commit", fail_commit)
    try:
        report = asyncio.run(ops._run(passwords(), APPROVAL))
    finally:
        event.remove(engine.sync_engine, "commit", fail_commit)
    assert report["committed"] == "UNKNOWN"
    assert report["code"] == "COMMIT_OUTCOME_UNKNOWN_REVIEW_REQUIRED"
    assert len(report["accounts"]) == 2
    assert counts(engine)["students"] == 0
    assert "synthetic-private" not in json.dumps(report)
