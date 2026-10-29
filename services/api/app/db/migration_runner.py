"""Explicit additive migration proposal. Import/default CLI never connects or applies DDL.

Own one dedicated migration connection throughout GET_LOCK/preflight/DDL/RELEASE_LOCK.
CREATE TABLE implicitly commits in MariaDB: this is NOT an atomic transaction/rollback.
The outside-repository manifest records intent before each statement and its observed
definition after success. An uncertain CREATE result is never automatically adopted.
"""

import argparse
import asyncio
import hashlib
import json
import os
import re
import ssl
from pathlib import Path
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, FilePath, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.db_connection import SESSION_CHARSET_SQL, TLSRequiredConnection
from app.core.event_loop import new_event_loop
from app.db.schema import initial_schema_sql

VERSION = "p0-initial-v1"
DDL_CHECKSUM = "157fae7e2d0798a39c2f048f29c605b1d5625b0cb1b8081985731285c0268a1b"
LOCK_NAME = "ditnow.schema.p0.initial.v1"
LEGACY = frozenset(
    {
        "auth_sessions",
        "courses",
        "course_sessions",
        "enrollments",
        "exams",
        "graduation_rules",
        "graduation_rule_categories",
        "question_logs",
        "students",
    }
)
HEX = r"^[0-9a-f]{64}$"
TIMEOUT = 5


class MigrationBlocked(RuntimeError):
    """Codes only. Never include SQL, credentials, host, paths or raw DB exceptions."""


class SafeArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        # argparse normally echoes rejected argument values, which may be secret mistakes.
        raise MigrationBlocked("ARGUMENTS_INVALID")


class MigrationCredentials(BaseSettings):
    """Separate CLI namespace, never runtime Settings or a login/role provisioning API."""

    model_config = SettingsConfigDict(
        env_prefix="DIT_MIGRATION_", env_file=None, extra="ignore", hide_input_in_errors=True
    )
    host: str = Field(repr=False, exclude=True)
    port: Literal[3307] = 3307
    database: Literal["ditnow"]
    user: Literal["ditnow_migrator"]
    password: SecretStr = Field(repr=False, exclude=True)
    tls_ca_file: FilePath = Field(repr=False, exclude=True)

    @field_validator("host")
    @classmethod
    def safe_host(cls, value):
        if not value or not value.isascii() or any(c.isspace() or c in "/\\@:#?[]" for c in value):
            raise ValueError("Explicit hostname or IPv4 required")
        return value

    @field_validator("password")
    @classmethod
    def nonempty_secret(cls, value):
        if not value.get_secret_value():
            raise ValueError("Migration password required")
        return value

    def endpoint_digest(self):
        # File bytes bind the approved CA file without publishing host, credential or path.
        material = [
            self.host,
            self.port,
            self.database,
            self.user,
            hashlib.sha256(self.tls_ca_file.read_bytes()).hexdigest(),
        ]
        return hashlib.sha256(json.dumps(material, separators=(",", ":")).encode()).hexdigest()


class Step(BaseModel):
    model_config = ConfigDict(extra="forbid")
    table: str
    statement_checksum: str = Field(pattern=HEX)
    state: Literal["NOT_STARTED", "PENDING", "APPLIED"] = "NOT_STARTED"
    definition_checksum: str | None = Field(default=None, pattern=HEX)


class Manifest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: Literal["p0-initial-v1"] = VERSION
    database: Literal["ditnow"] = "ditnow"
    ddl_checksum: str = Field(pattern=HEX)
    endpoint_checksum: str = Field(pattern=HEX)
    legacy_definitions: dict[str, str]
    steps: list[Step]


class MigrationConnection(Protocol):
    endpoint_checksum: str

    async def query(self, sql: str, parameters: tuple = ()) -> list[tuple]: ...
    def close(self) -> None: ...


class DriverConnection:
    """Minimal adapter used by the explicit CLI only; never registered as app dependency."""

    def __init__(self, connection, endpoint_checksum):
        self.connection, self.endpoint_checksum = connection, endpoint_checksum

    async def query(self, sql, parameters=()):
        try:
            async with asyncio.timeout(TIMEOUT):
                async with self.connection.cursor() as cursor:
                    await cursor.execute(sql, parameters)
                    return list(await cursor.fetchall()) if cursor.description else []
        except Exception:
            raise MigrationBlocked("DATABASE_OPERATION_FAILED") from None

    def close(self):
        self.connection.close()


async def connect_migrator(credentials: MigrationCredentials) -> DriverConnection:
    """Reuse the reviewed pre-auth TLS guard, with a separate, non-runtime credential object."""
    raw = None
    try:
        context = ssl.create_default_context(cafile=str(credentials.tls_ca_file))
        if not context.check_hostname or context.verify_mode != ssl.CERT_REQUIRED:
            raise MigrationBlocked("VERIFIED_TLS_REQUIRED")
        endpoint = credentials.endpoint_digest()
        raw = TLSRequiredConnection(
            host=credentials.host,
            port=credentials.port,
            user=credentials.user,
            password=credentials.password.get_secret_value(),
            db=credentials.database,
            charset="utf8mb4",
            init_command=SESSION_CHARSET_SQL,
            connect_timeout=TIMEOUT,
            ssl=context,
            local_infile=False,
            autocommit=False,
            echo=False,
        )
        async with asyncio.timeout(TIMEOUT):
            await raw._connect()
        return DriverConnection(raw, endpoint)
    except BaseException as exc:
        if raw is not None:
            raw.close()
        if not isinstance(exc, Exception):
            raise
        raise MigrationBlocked("MIGRATION_CONNECTION_FAILED") from None


def plan() -> list[tuple[str, str]]:
    path = Path(__file__).parent / "migrations" / "0001_initial.review.sql"
    sql = path.read_text(encoding="utf-8")  # Universal newlines: identical SHA on Windows/Linux.
    if hashlib.sha256(sql.encode()).hexdigest() != DDL_CHECKSUM or sql != initial_schema_sql():
        raise MigrationBlocked("REVIEWED_DDL_CHANGED")
    statements = sql[sql.index("CREATE TABLE ") :].strip().split(";\n\n")
    result = []
    for statement in statements:
        statement = statement.removesuffix(";")
        match = re.match(r"CREATE TABLE ([a-z_]+) \(", statement)
        if not match or ";" in statement:
            raise MigrationBlocked("CREATE_ONLY_PLAN_REQUIRED")
        result.append((match[1], statement))
    names = {table for table, _ in result}
    if len(result) != 16 or len(names) != 16 or names & LEGACY:
        raise MigrationBlocked("PLAN_TARGETS_INVALID")
    return result


def state_path(path: Path) -> Path:
    if not path.is_absolute() or path.is_symlink():
        raise MigrationBlocked("OUTSIDE_REPOSITORY_MANIFEST_REQUIRED")
    result = path.resolve()
    if not result.parent.is_dir() or any((parent / ".git").exists() for parent in result.parents):
        raise MigrationBlocked("OUTSIDE_REPOSITORY_MANIFEST_REQUIRED")
    pending = result.with_name(result.name + ".pending-write")
    if pending.exists() or pending.is_symlink():
        raise MigrationBlocked("MANIFEST_RECOVERY_REQUIRED")
    if result.exists() and (not result.is_file() or result.stat().st_size > 1024 * 1024):
        raise MigrationBlocked("MANIFEST_INVALID")
    return result


def write_manifest(path: Path, manifest: Manifest):
    """Same-directory replace + file fsync; operator must secure the outside state directory."""
    temporary = path.with_name(path.name + ".pending-write")
    descriptor = None
    try:
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as output:
            descriptor = None
            output.write(manifest.model_dump_json(indent=2) + "\n")
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    except Exception:
        if descriptor is not None:
            os.close(descriptor)
        # Never delete a leftover temporary file: an operator must reconcile it explicitly.
        raise MigrationBlocked("MANIFEST_WRITE_FAILED") from None


async def legacy_snapshot(connection: MigrationConnection):
    return {name: await definition(connection, name) for name in sorted(LEGACY)}


async def definition(connection: MigrationConnection, table: str):
    if not re.fullmatch(r"[a-z_]+", table):
        raise MigrationBlocked("INVALID_TABLE_IDENTIFIER")
    rows = await connection.query(f"SHOW CREATE TABLE `ditnow`.`{table}`")
    if len(rows) != 1 or len(rows[0]) < 2 or not isinstance(rows[0][1], str):
        raise MigrationBlocked("TABLE_DEFINITION_UNAVAILABLE")
    # Preserve exact server definition, including options. No whitespace/collation normalization.
    return hashlib.sha256(rows[0][1].encode()).hexdigest()


async def table_names(connection):
    rows = await connection.query("SHOW FULL TABLES FROM `ditnow`")
    if any(len(row) != 2 or row[1] != "BASE TABLE" for row in rows):
        raise MigrationBlocked("UNEXPECTED_SCHEMA_OBJECT")
    return {row[0] for row in rows}


async def preflight(connection):
    rows = await connection.query(
        "SELECT DATABASE(), CURRENT_USER(), VERSION(), "
        "@@collation_connection, @@foreign_key_checks, @@check_constraint_checks, @@sql_mode"
    )
    if len(rows) != 1 or len(rows[0]) != 7:
        raise MigrationBlocked("PREFLIGHT_FAILED")
    database, user, version, collation, fk, checks, mode = rows[0]
    if database != "ditnow" or str(user).split("@")[0] != "ditnow_migrator":
        raise MigrationBlocked("WRONG_DATABASE_OR_MIGRATOR")
    if not str(version).startswith("11.4.") or "MariaDB" not in str(version):
        raise MigrationBlocked("SERVER_VERSION_UNAPPROVED")
    if (
        collation != "utf8mb4_unicode_ci"
        or fk != 1
        or checks != 1
        or not ({"STRICT_ALL_TABLES", "STRICT_TRANS_TABLES"} & set(str(mode).split(",")))
    ):
        raise MigrationBlocked("CONNECTION_CONSTRAINT_SETTINGS_INVALID")


async def run_migration(
    connection: MigrationConnection,
    path: Path,
    expected_checksum: str,
    *,
    apply: bool = False,
    resume: bool = False,
):
    """Takes ownership of the dedicated connection; closes it on every exit.

    A manifest is local to one approved endpoint and version. APPLIED tables must match
    their recorded exact definitions; PENDING+existing table is an ambiguous outcome and
    BLOCKED for manual reconciliation, never an automatic skip or destructive rollback.
    """
    locked = False
    local_descriptor = None
    local_lock = None
    try:
        statements = plan()
        if expected_checksum != DDL_CHECKSUM:
            raise MigrationBlocked("CHECKSUM_CONFIRMATION_REQUIRED")
        path = state_path(path)
        if apply:
            # Also prevent two endpoints/processes from reusing the same outside manifest.
            local_lock = path.with_name(path.name + ".migration-lock")
            try:
                local_descriptor = os.open(local_lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                os.write(local_descriptor, str(os.getpid()).encode("ascii"))
                os.fsync(local_descriptor)
            except Exception:
                raise MigrationBlocked("EXCLUSIVE_MANIFEST_LOCK_REQUIRED") from None
        result = await connection.query("SELECT GET_LOCK(%s, %s)", (LOCK_NAME, TIMEOUT))
        if result != [(1,)]:
            raise MigrationBlocked("MIGRATION_LOCK_UNAVAILABLE")
        locked = True
        await preflight(connection)
        names = await table_names(connection)
        if not LEGACY.issubset(names):
            raise MigrationBlocked("LEGACY_BASELINE_MISSING")
        baseline = await legacy_snapshot(connection)
        if path.exists():
            if not resume:
                raise MigrationBlocked("EXPLICIT_RESUME_REQUIRED")
            try:
                manifest = Manifest.model_validate_json(path.read_text(encoding="utf-8"))
            except Exception:
                raise MigrationBlocked("MANIFEST_INVALID") from None
            if (
                manifest.ddl_checksum != DDL_CHECKSUM
                or manifest.endpoint_checksum != connection.endpoint_checksum
                or manifest.legacy_definitions != baseline
                or len(manifest.steps) != len(statements)
            ):
                raise MigrationBlocked("MANIFEST_BASELINE_MISMATCH")
        else:
            if resume:
                raise MigrationBlocked("RESUME_MANIFEST_MISSING")
            manifest = Manifest(
                ddl_checksum=DDL_CHECKSUM,
                endpoint_checksum=connection.endpoint_checksum,
                legacy_definitions=baseline,
                steps=[
                    Step(table=table, statement_checksum=hashlib.sha256(sql.encode()).hexdigest())
                    for table, sql in statements
                ],
            )
        applied = set()
        pending_seen = False
        for step, (table, sql) in zip(manifest.steps, statements, strict=True):
            if (
                step.table != table
                or step.statement_checksum != hashlib.sha256(sql.encode()).hexdigest()
            ):
                raise MigrationBlocked("MANIFEST_PLAN_MISMATCH")
            if step.state == "APPLIED":
                if (
                    pending_seen
                    or table not in names
                    or step.definition_checksum != await definition(connection, table)
                ):
                    raise MigrationBlocked("APPLIED_DEFINITION_MISMATCH")
                applied.add(table)
            else:
                pending_seen = True
                if step.definition_checksum is not None or table in names:
                    raise MigrationBlocked("UNRECORDED_OR_UNCERTAIN_TARGET")
        if names != LEGACY | applied:
            raise MigrationBlocked("UNEXPECTED_EXISTING_TARGET")
        if not apply:
            return {
                "mode": "INSPECT",
                "ready": True,
                "remaining": 16 - len(applied),
                "persistent_writes": 0,
            }
        if not path.exists():
            write_manifest(path, manifest)
        for step, (_, sql) in zip(manifest.steps, statements, strict=True):
            if step.state == "APPLIED":
                continue
            if await connection.query(
                "SELECT IS_USED_LOCK(%s) = CONNECTION_ID()", (LOCK_NAME,)
            ) != [(1,)]:
                raise MigrationBlocked("MIGRATION_LOCK_LOST")
            if await legacy_snapshot(connection) != baseline:
                raise MigrationBlocked("LEGACY_DEFINITION_CHANGED")
            if await table_names(connection) != LEGACY | applied:
                raise MigrationBlocked("SCHEMA_CHANGED_DURING_APPLY")
            step.state = "PENDING"
            write_manifest(path, manifest)
            await connection.query(sql)
            # The CREATE may already have committed if any following check or write fails.
            fingerprint = await definition(connection, step.table)
            if await legacy_snapshot(connection) != baseline:
                raise MigrationBlocked("LEGACY_DEFINITION_CHANGED")
            if await table_names(connection) != LEGACY | applied | {step.table}:
                raise MigrationBlocked("SCHEMA_CHANGED_DURING_APPLY")
            step.definition_checksum = fingerprint
            step.state = "APPLIED"
            write_manifest(path, manifest)
            applied.add(step.table)
        return {
            "mode": "APPLY",
            "complete": True,
            "applied_statements": len(applied),
            "version": VERSION,
            "ddl_checksum": DDL_CHECKSUM,
            "rollback": "NOT_AVAILABLE",
        }
    except MigrationBlocked:
        raise
    except Exception:
        raise MigrationBlocked("MIGRATION_STOPPED_REVIEW_MANIFEST") from None
    finally:
        if locked:
            try:
                await connection.query("SELECT RELEASE_LOCK(%s)", (LOCK_NAME,))
            except Exception:
                pass  # Terminating the dedicated connection also releases GET_LOCK.
        connection.close()
        if local_descriptor is not None:
            os.close(local_descriptor)
            try:
                local_lock.unlink()
            except OSError:
                pass  # A leftover file fails closed; operator reconciliation required.


async def _live(args):
    credentials = MigrationCredentials()
    connection = await connect_migrator(credentials)
    return await run_migration(
        connection,
        Path(args.manifest),
        args.expected_checksum,
        apply=args.apply,
        resume=args.resume,
    )


def main(argv=None):
    parser = SafeArgumentParser(description="Explicit CREATE-only migration; default offline plan")
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--inspect", action="store_true")
    modes.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm-database", choices=["ditnow"])
    parser.add_argument("--expected-checksum")
    parser.add_argument("--manifest")
    parser.add_argument("--resume", action="store_true")
    try:
        args = parser.parse_args(argv)
        statements = plan()
        if not args.inspect and not args.apply:
            if any([args.confirm_database, args.expected_checksum, args.manifest, args.resume]):
                raise MigrationBlocked("LIVE_MODE_REQUIRED_FOR_OPTIONS")
            report = {
                "mode": "DRY_RUN",
                "connection": "NOT_RUN",
                "version": VERSION,
                "ddl_checksum": DDL_CHECKSUM,
                "statements": len(statements),
                "persistent_writes": 0,
            }
        else:
            if (
                args.confirm_database != "ditnow"
                or args.expected_checksum != DDL_CHECKSUM
                or not args.manifest
            ):
                raise MigrationBlocked("EXPLICIT_TARGET_CHECKSUM_MANIFEST_REQUIRED")
            # Validate local path before credentials/TLS/network are touched.
            state_path(Path(args.manifest))
            with asyncio.Runner(loop_factory=new_event_loop) as runner:
                report = runner.run(_live(args))
        print(json.dumps(report))
        return 0
    except MigrationBlocked as exc:
        print(json.dumps({"status": "BLOCKED", "code": str(exc), "rollback": "NOT_CLAIMED"}))
        return 2
    except Exception:
        print(
            json.dumps(
                {
                    "status": "BLOCKED",
                    "code": "CONFIGURATION_OR_IO_FAILED",
                    "rollback": "NOT_CLAIMED",
                }
            )
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
