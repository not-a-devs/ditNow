"""Explicit operator CLI: create exactly two synthetic DEMO student accounts. Default DRY_RUN.

TASK-DEMO-ACCOUNT-OPS. Import and the default CLI never read Settings, passwords or the
network. ``--apply`` needs an approval reference, the synthetic-only confirmation and two
externally injected passwords (environment only, never argv/defaults). It uses the strict
``ditnow_app`` runtime factory, CREATEs only new rows in one transaction and commits once.
No DDL/create_all/drop/reset/GRANT/admin role, no adopt/overwrite/password reset.
Collision checks read only fixed synthetic keys; no other existing record is selected.
The audit rows grant nothing alone: runtime requires an operator-reviewed audit UUID allowlist.
"""

import argparse
import asyncio
import json
import re
from collections.abc import Awaitable, Callable
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID, uuid4

from chatbot.app.auth import hash_password
from chatbot.app.models import StudentRow
from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import event, func, inspect, or_, select, text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, AsyncSession
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.db_connection import create_database_engine
from app.core.event_loop import new_event_loop
from app.db.live_check import schema_readiness
from app.db.migration_runner import LEGACY
from app.db.models import (
    AcademicMembershipRow,
    AuditLogRow,
    Base,
    DepartmentRow,
    IdentityRow,
    OpportunityRow,
    ProfileRow,
    RoleAssignmentRow,
    subject_digest,
)
from app.schemas.common import utc_now

STUDENT_ISSUER = "urn:ditnow:student-login:demo:v1"
# Audit-only synthetic actor: different issuer, disabled, no role/profile/legacy login row.
OPERATOR_ISSUER = "urn:ditnow:demo-audit-operator:v1"
OPERATOR_SUBJECT = "DITDEMO_AUDIT_OPERATOR"
AUDIT_EVENT = "identity_binding_approved"
AUDIT_RESOURCE = "identity_binding"
OPPORTUNITY_MARKER = "DITNOW_DEMO_P0_INTEGRATION"
OPPORTUNITY_TITLE = "[가상] 통합검증용 기회 " + OPPORTUNITY_MARKER
PASSWORD_ENV = ("DIT_DEMO_ACCOUNT_PASSWORD_A", "DIT_DEMO_ACCOUNT_PASSWORD_B")
REQUIRED_TABLES = tuple(sorted(set(Base.metadata.tables) | LEGACY))
APPROVAL_REFERENCE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{2,63}")
ALLOWED_VERBS = frozenset({"SELECT", "SHOW", "INSERT", "SAVEPOINT", "RELEASE", "ROLLBACK"})


@dataclass(frozen=True)
class SyntheticStudent:
    student_id: str
    display_name: str
    department_code: str
    department_name: str


STUDENTS = (
    SyntheticStudent("DITDEMO_A", "[가상]학생A", "DEMO-A", "[가상] 통합검증 학과A"),
    SyntheticStudent("DITDEMO_B", "[가상]학생B", "DEMO-B", "[가상] 통합검증 학과B"),
)
PLANNED_ROWS = {
    "identities": 3,
    "profiles": 2,
    "departments": 2,
    "academic_memberships": 2,
    "role_assignments": 2,
    "students": 2,
    "audit_logs": 2,
    "opportunities": 1,
}


class DemoAccountBlocked(RuntimeError):
    """Static codes only. Never attach passwords, hashes, DSN, SQL or driver errors."""


def require(value, code: str) -> None:
    if not value:
        raise DemoAccountBlocked(code)


class SafeArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        # argparse echoes rejected values; a mistaken password argument must never be printed.
        raise DemoAccountBlocked("ARGUMENTS_INVALID")


class DemoAccountPasswords(BaseSettings):
    """Two operator-injected secrets. No default, argv, dotenv or secrets-directory source."""

    model_config = SettingsConfigDict(
        env_prefix="DIT_DEMO_ACCOUNT_", env_file=None, extra="ignore", hide_input_in_errors=True
    )
    password_a: SecretStr = Field(repr=False, exclude=True)
    password_b: SecretStr = Field(repr=False, exclude=True)

    @field_validator("password_a", "password_b")
    @classmethod
    def acceptable(cls, value: SecretStr) -> SecretStr:
        raw = value.get_secret_value()
        # Login accepts 1..64 code points without normalization; require a non-trivial value.
        if not 12 <= len(raw) <= 64 or raw.strip() != raw or any(ord(c) < 32 for c in raw):
            raise ValueError("Synthetic password policy not met")
        return value

    @model_validator(mode="after")
    def distinct(self) -> "DemoAccountPasswords":
        a, b = self.password_a.get_secret_value(), self.password_b.get_secret_value()
        if a == b or any(s.student_id.casefold() in p.casefold() for s in STUDENTS for p in (a, b)):
            raise ValueError("Synthetic passwords must be distinct and not contain student IDs")
        return self


@dataclass(frozen=True)
class AccountIds:
    identity_id: UUID = field(default_factory=uuid4)
    department_id: UUID = field(default_factory=uuid4)
    membership_id: UUID = field(default_factory=uuid4)
    role_assignment_id: UUID = field(default_factory=uuid4)
    audit_log_id: UUID = field(default_factory=uuid4)


@dataclass(frozen=True)
class ProvisionPlan:
    operator_id: UUID = field(default_factory=uuid4)
    opportunity_id: UUID = field(default_factory=uuid4)
    accounts: tuple[AccountIds, AccountIds] = field(
        default_factory=lambda: (AccountIds(), AccountIds())
    )

    def all_ids(self) -> list[UUID]:
        values = [self.operator_id, self.opportunity_id]
        for ids in self.accounts:
            values += [
                ids.identity_id,
                ids.department_id,
                ids.membership_id,
                ids.role_assignment_id,
                ids.audit_log_id,
            ]
        return values


@dataclass
class CommitOutcome:
    """Non-secret outcome survives connection context exit, cancellation and cleanup errors."""

    plan: ProvisionPlan | None = None
    attempted: bool = False
    confirmed: bool = False

    def failure_report(self, code: str, approval_reference: str) -> dict[str, object]:
        committed = "YES" if self.confirmed else "UNKNOWN" if self.attempted else "NO"
        report = {"status": "BLOCKED", "code": code, "committed": committed}
        if self.attempted and self.plan is not None:
            report.update(metadata(self.plan, approval_reference))
        return report


async def require_readiness(connection: AsyncConnection) -> None:
    """Metadata only: server, app account, 25 InnoDB tables and columns. No record reads."""
    require(connection.dialect.name in {"mysql", "mariadb"}, "MARIADB_REQUIRED")
    version, collation, database, user, foreign_keys, checks = (
        await connection.execute(
            text(
                "SELECT VERSION(), @@collation_connection, DATABASE(), CURRENT_USER(), "
                "@@foreign_key_checks, @@check_constraint_checks"
            )
        )
    ).one()
    require(str(version).startswith("11.4.") and "MariaDB" in str(version), "SERVER_VERSION")
    require(collation == "utf8mb4_unicode_ci" and database == "ditnow", "SESSION_CONFIGURATION")
    require(str(user).split("@")[0] == "ditnow_app", "RUNTIME_APP_ACCOUNT_REQUIRED")
    require(foreign_keys == 1 and checks == 1, "CONSTRAINT_CHECKS_DISABLED")
    ready = await connection.run_sync(schema_readiness)
    require(ready["column_names_ready"], "SCHEMA_NOT_READY")
    legacy_columns = await connection.run_sync(
        lambda conn: {column["name"] for column in inspect(conn).get_columns("students")}
    )
    require(set(StudentRow.__table__.columns.keys()) <= legacy_columns, "LEGACY_STUDENTS_NOT_READY")
    require(len(REQUIRED_TABLES) == 25, "TABLE_CONTRACT_CHANGED")
    placeholders = ",".join(f":t{i}" for i in range(len(REQUIRED_TABLES)))
    values = {f"t{i}": name for i, name in enumerate(REQUIRED_TABLES)}
    engines = (
        await connection.execute(
            text(
                "SELECT TABLE_NAME, ENGINE FROM information_schema.TABLES "
                f"WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME IN ({placeholders})"
            ),
            values,
        )
    ).all()
    require(
        len(engines) == 25
        and {row[0] for row in engines} == set(REQUIRED_TABLES)
        and all(str(row[1]).casefold() == "innodb" for row in engines),
        "INNODB_25_TABLES_REQUIRED",
    )
    triggers = (
        await connection.execute(
            text(
                "SELECT COUNT(*) FROM information_schema.TRIGGERS "
                f"WHERE TRIGGER_SCHEMA=DATABASE() AND EVENT_OBJECT_TABLE IN ({placeholders})"
            ),
            values,
        )
    ).scalar_one()
    require(triggers == 0, "VISIBLE_TRIGGERS_BLOCKED")


def collisions(session: Session) -> list[str]:
    """Return conflict kinds only. Reads fixed synthetic keys, never other rows' contents."""
    student_ids = [s.student_id for s in STUDENTS]
    bindings = [(STUDENT_ISSUER, sid) for sid in student_ids] + [
        (OPERATOR_ISSUER, OPERATOR_SUBJECT)
    ]
    found = []
    if session.scalar(
        select(func.count()).select_from(StudentRow).where(StudentRow.student_id.in_(student_ids))
    ):
        found.append("SYNTHETIC_STUDENT_ID_EXISTS")
    identity_match = or_(
        IdentityRow.binding_digest.in_([subject_digest(i, s) for i, s in bindings]),
        *[(IdentityRow.issuer == i) & (IdentityRow.subject == s) for i, s in bindings],
    )
    if session.scalar(select(func.count()).select_from(IdentityRow).where(identity_match)):
        found.append("SYNTHETIC_ISSUER_SUBJECT_EXISTS")
    codes = [s.department_code for s in STUDENTS]
    if session.scalar(
        select(func.count()).select_from(DepartmentRow).where(DepartmentRow.code.in_(codes))
    ):
        found.append("SYNTHETIC_DEPARTMENT_CODE_EXISTS")
    return found


def insert_rows(session: Session, plan: ProvisionPlan, hashes: tuple[str, str], now: datetime):
    """CREATE only. Canonical membership/role rows are the sole authority after creation."""
    session.add(
        IdentityRow(
            id=plan.operator_id,
            issuer=OPERATOR_ISSUER,
            subject=OPERATOR_SUBJECT,
            status="disabled",
            source_kind="DEMO",
        )
    )
    for spec, ids in zip(STUDENTS, plan.accounts, strict=True):
        session.add(
            DepartmentRow(
                id=ids.department_id,
                code=spec.department_code,
                name=spec.department_name,
                source_kind="DEMO",
            )
        )
        session.add(
            IdentityRow(
                id=ids.identity_id,
                issuer=STUDENT_ISSUER,
                subject=spec.student_id,
                status="active",
                source_kind="DEMO",
            )
        )
    session.flush()
    for spec, ids, password_hash in zip(STUDENTS, plan.accounts, hashes, strict=True):
        session.add(
            ProfileRow(user_id=ids.identity_id, display_name=spec.display_name, source_kind="DEMO")
        )
        session.add(
            AcademicMembershipRow(
                id=ids.membership_id,
                user_id=ids.identity_id,
                department_id=ids.department_id,
                academic_year=1,
                status="active",
                valid_from=now,
                source_kind="DEMO",
            )
        )
        session.add(
            RoleAssignmentRow(
                id=ids.role_assignment_id,
                user_id=ids.identity_id,
                role="student",
                scope_type="department",
                scope_id=ids.department_id,
                status="active",
                valid_from=now,
                source_kind="DEMO",
            )
        )
        # Legacy login authority keeps only its required initial fields (matching values).
        session.add(
            StudentRow(
                student_id=spec.student_id,
                name=spec.display_name,
                dept_id=spec.department_code,
                grade=1,
                password_hash=password_hash,
            )
        )
        session.add(
            AuditLogRow(
                id=ids.audit_log_id,
                event=AUDIT_EVENT,
                resource_kind=AUDIT_RESOURCE,
                actor_id=plan.operator_id,
                entity_id=ids.identity_id,
                source_kind="DEMO",
            )
        )
    session.add(
        OpportunityRow(
            id=plan.opportunity_id,
            kind="contest",
            title=OPPORTUNITY_TITLE,
            organization="",
            eligibility="가상 통합검증 데이터",
            status="published",
            target_scope={"level": "school"},
            files=[],
            submission_mode="info_only",
            source_kind="DEMO",
            source_url=None,
            checked_at=None,
            original_url=None,
        )
    )
    session.flush()


def own_row_counts(session: Session, plan: ProvisionPlan) -> dict[str, int]:
    users = [ids.identity_id for ids in plan.accounts]
    everyone = [plan.operator_id, *users]

    def count(model, predicate):
        return session.scalar(select(func.count()).select_from(model).where(predicate))

    return {
        "identities": count(IdentityRow, IdentityRow.id.in_(everyone)),
        "profiles": count(ProfileRow, ProfileRow.user_id.in_(everyone)),
        "departments": count(
            DepartmentRow, DepartmentRow.id.in_([ids.department_id for ids in plan.accounts])
        ),
        "academic_memberships": count(
            AcademicMembershipRow, AcademicMembershipRow.user_id.in_(everyone)
        ),
        "role_assignments": count(RoleAssignmentRow, RoleAssignmentRow.user_id.in_(everyone)),
        "non_student_roles": count(
            RoleAssignmentRow,
            RoleAssignmentRow.user_id.in_(everyone) & (RoleAssignmentRow.role != "student"),
        ),
        "students": count(StudentRow, StudentRow.student_id.in_([s.student_id for s in STUDENTS])),
        "audit_logs": count(AuditLogRow, AuditLogRow.actor_id == plan.operator_id),
        "opportunities": count(OpportunityRow, OpportunityRow.id == plan.opportunity_id),
    }


class WriteGuard:
    """Connection-scoped: CREATE-only verbs, and exactly one explicitly armed commit."""

    def __init__(self):
        self.commit_armed = False
        self.commits = 0

    def statement(self, conn, cursor, statement, parameters, context, many):
        verb = statement.lstrip().split(None, 1)[0].upper() if statement.strip() else ""
        if verb not in ALLOWED_VERBS or ";" in statement:
            raise DemoAccountBlocked("STATEMENT_BLOCKED")

    def commit(self, conn):
        if not self.commit_armed or self.commits:
            raise DemoAccountBlocked("COMMIT_BLOCKED")
        self.commits += 1


@contextmanager
def write_guards(connection):
    guard = WriteGuard()
    event.listen(connection, "before_cursor_execute", guard.statement)
    event.listen(connection, "commit", guard.commit)
    try:
        yield guard
    finally:
        event.remove(connection, "before_cursor_execute", guard.statement)
        event.remove(connection, "commit", guard.commit)


def metadata(plan: ProvisionPlan, approval_reference: str) -> dict[str, object]:
    """Non-secret identifiers for root's protected capture. No password, hash or DSN."""
    return {
        "approval_reference": approval_reference,
        "issuer": STUDENT_ISSUER,
        "accounts": [
            {
                "student_id": spec.student_id,
                "identity_id": str(ids.identity_id),
                "display_name": spec.display_name,
                "department_id": str(ids.department_id),
                "department_code": spec.department_code,
                "membership_id": str(ids.membership_id),
                "academic_year": 1,
                "role_assignment_id": str(ids.role_assignment_id),
                "role": "student",
                "role_scope": "department",
                "audit_log_id": str(ids.audit_log_id),
            }
            for spec, ids in zip(STUDENTS, plan.accounts, strict=True)
        ],
        "operator_identity_id": str(plan.operator_id),
        "operator_identity": {"status": "disabled", "roles": 0, "login": "NONE"},
        "audit_log_ids": [str(ids.audit_log_id) for ids in plan.accounts],
        "opportunity_id": str(plan.opportunity_id),
        "opportunity_marker": OPPORTUNITY_MARKER,
        "runtime_audit_allowlist": "OPERATOR_REVIEW_REQUIRED",
        "secret_material": "NOT_OUTPUT",
    }


async def provision(
    engine: AsyncEngine,
    passwords: DemoAccountPasswords,
    approval_reference: str,
    *,
    readiness: Callable[[AsyncConnection], Awaitable[None]] = require_readiness,
    clock: Callable[[], datetime] = utc_now,
    outcome: CommitOutcome | None = None,
) -> dict[str, object]:
    require(APPROVAL_REFERENCE.fullmatch(approval_reference or ""), "APPROVAL_REFERENCE_REQUIRED")
    plan = ProvisionPlan()
    outcome = outcome if outcome is not None else CommitOutcome()
    outcome.plan = plan
    require(len(set(plan.all_ids())) == 12 and all(v.int for v in plan.all_ids()), "UUID_PLAN")
    # PBKDF2 before the transaction keeps the write window short; hashes never leave this frame.
    hashes = (
        hash_password(passwords.password_a.get_secret_value()),
        hash_password(passwords.password_b.get_secret_value()),
    )
    async with engine.connect() as connection:
        with write_guards(connection.sync_connection) as guard:
            await readiness(connection)
            await connection.rollback()  # end metadata autobegin before the single write UOW
            transaction = await connection.begin()
            try:
                async with AsyncSession(
                    bind=connection,
                    autoflush=False,
                    expire_on_commit=False,
                    join_transaction_mode="rollback_only",
                ) as session:
                    conflicts = await session.run_sync(collisions)
                    if conflicts:
                        raise DemoAccountBlocked("COLLISION:" + ",".join(conflicts))
                    now = clock()
                    require(now.tzinfo is not None and now.utcoffset() is not None, "CLOCK")
                    await session.run_sync(insert_rows, plan, hashes, now)
                    counts = await session.run_sync(own_row_counts, plan)
                    require(_planned(counts), "PRECOMMIT_COUNT_MISMATCH")
            except BaseException:
                if transaction.is_active:
                    await transaction.rollback()
                # A blocked commit/statement may leave the DBAPI transaction open.
                await connection.run_sync(lambda conn: conn.connection.rollback())
                raise
            guard.commit_armed = True
            outcome.attempted = True
            try:
                await transaction.commit()
            except BaseException:
                raise DemoAccountBlocked("COMMIT_OUTCOME_UNKNOWN_REVIEW_REQUIRED") from None
            outcome.confirmed = True
            guard.commit_armed = False
            # Committed: always return identifiers. Fresh read of own keys only, then roll back.
            try:
                async with AsyncSession(bind=connection, expire_on_commit=False) as session:
                    verified = await session.run_sync(own_row_counts, plan)
                await connection.rollback()
                verification = "MATCHED" if _planned(verified) else "MISMATCH_REVIEW_REQUIRED"
            except Exception:
                verification = "NOT_VERIFIED_REVIEW_REQUIRED"
    return {
        "status": "APPLIED",
        "mode": "APPLY",
        "commits": guard.commits,
        "rows_created": PLANNED_ROWS,
        "post_commit_verification": verification,
        **metadata(plan, approval_reference),
    }


def _planned(counts: dict[str, int]) -> bool:
    rows = {key: value for key, value in counts.items() if key != "non_student_roles"}
    return rows == PLANNED_ROWS and counts["non_student_roles"] == 0


def dry_run_report() -> dict[str, object]:
    return {
        "mode": "DRY_RUN",
        "connection": "NOT_RUN",
        "settings": "NOT_READ",
        "passwords": "NOT_READ",
        "persistent_writes": 0,
        "issuer": STUDENT_ISSUER,
        "student_ids": [s.student_id for s in STUDENTS],
        "department_codes": [s.department_code for s in STUDENTS],
        "planned_rows": PLANNED_ROWS,
        "required_tables": len(REQUIRED_TABLES),
        "apply_requires": [
            "--apply",
            "--confirm-synthetic-only",
            "--approval-reference",
            *PASSWORD_ENV,
            "Settings(ditnow_app, verified TLS)",
        ],
    }


async def _run(passwords: DemoAccountPasswords, approval_reference: str) -> dict[str, object]:
    engine = None
    outcome = CommitOutcome()
    try:
        settings = Settings()
        require(settings.database_configured, "DATABASE_NOT_CONFIGURED")
        require(settings.db_user == "ditnow_app", "RUNTIME_APP_ACCOUNT_REQUIRED")
        engine = create_database_engine(settings)
        async with asyncio.timeout(120):
            return await provision(engine, passwords, approval_reference, outcome=outcome)
    except DemoAccountBlocked as exc:
        code = str(exc)
        return outcome.failure_report(code, approval_reference)
    except Exception:
        if outcome.confirmed:
            code = "POST_COMMIT_FAILURE_REVIEW_REQUIRED"
        elif outcome.attempted:
            code = "COMMIT_OUTCOME_UNKNOWN_REVIEW_REQUIRED"
        else:
            code = "CONFIGURATION_FAILED" if engine is None else "FAILED_BEFORE_COMMIT"
        return outcome.failure_report(code, approval_reference)
    finally:
        if engine is not None:
            try:
                await engine.dispose()
            except Exception:
                pass  # Never surface driver details; the process exits right after.


def main(argv=None) -> int:
    parser = SafeArgumentParser(description="Synthetic DEMO accounts; default offline DRY_RUN")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm-synthetic-only", action="store_true")
    parser.add_argument("--approval-reference")
    try:
        args = parser.parse_args(argv)
        if not args.apply:
            require(
                not args.confirm_synthetic_only and args.approval_reference is None,
                "APPLY_REQUIRED_FOR_OPTIONS",
            )
            print(json.dumps(dry_run_report(), ensure_ascii=False))
            return 0
        require(args.confirm_synthetic_only, "SYNTHETIC_ONLY_CONFIRMATION_REQUIRED")
        require(
            APPROVAL_REFERENCE.fullmatch(args.approval_reference or ""),
            "APPROVAL_REFERENCE_REQUIRED",
        )
        try:
            passwords = DemoAccountPasswords()
        except Exception:
            raise DemoAccountBlocked("INJECTED_PASSWORDS_REQUIRED") from None
        with asyncio.Runner(loop_factory=new_event_loop) as runner:
            report = runner.run(_run(passwords, args.approval_reference))
    except DemoAccountBlocked as exc:
        report = {"status": "BLOCKED", "code": str(exc), "persistent_writes": 0}
    except Exception:
        report = {"status": "BLOCKED", "code": "CONFIGURATION_FAILED", "persistent_writes": 0}
    print(json.dumps(report, ensure_ascii=False))
    return 0 if report.get("status") == "APPLIED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
