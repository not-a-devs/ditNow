"""Explicit opt-in, read-only MariaDB schema check. Never applies DDL or seeds."""

import asyncio
import json
import os
from collections.abc import Mapping

from sqlalchemy import inspect, text
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.config import Settings
from app.core.db_connection import create_database_engine
from app.core.event_loop import new_event_loop
from app.db.models import Base


def schema_readiness(connection: Connection) -> dict[str, object]:
    """Inspect names/types only; never select student or operational records."""
    inspector = inspect(connection)
    actual = set(inspector.get_table_names())
    expected = set(Base.metadata.tables)
    missing = sorted(expected - actual)
    missing_columns: dict[str, list[str]] = {}
    for name in sorted(expected & actual):
        columns = {column["name"] for column in inspector.get_columns(name)}
        absent = sorted(set(Base.metadata.tables[name].columns.keys()) - columns)
        if absent:
            missing_columns[name] = absent
    return {
        "expected_tables": len(expected),
        "missing_tables": missing,
        "missing_columns": missing_columns,
        "column_names_ready": not missing and not missing_columns,
        # Names alone cannot establish FK/CHECK/index/GRANT/transaction correctness.
        "constraints_and_grants": "NOT_RUN",
        "record_reads": 0,
        "persistent_writes": 0,
    }


async def read_only_report(engine: AsyncEngine) -> Mapping[str, object]:
    async with engine.connect() as connection:
        server = (
            await connection.execute(text("SELECT VERSION(), @@collation_connection, DATABASE()"))
        ).one()
        schema = await connection.run_sync(schema_readiness)
        # The strict factory enforces TLS before authentication; no insecure fallback.
        return {
            "connection": "VERIFIED_TLS",
            "expected_mariadb_11_4": str(server[0]).startswith("11.4.")
            and "MariaDB" in str(server[0]),
            "expected_connection_collation": server[1] == "utf8mb4_unicode_ci",
            "expected_schema": server[2] == "ditnow",
            **schema,
        }


async def _run() -> int:
    engine = None
    try:
        engine = create_database_engine(Settings())
        report = await read_only_report(engine)
        print(json.dumps(report))
        return (
            0
            if all(
                report[key]
                for key in (
                    "expected_mariadb_11_4",
                    "expected_connection_collation",
                    "expected_schema",
                    "column_names_ready",
                )
            )
            else 3
        )
    except Exception:
        # Drivers/validation errors may contain hosts, credentials, SQL or parameters.
        print(json.dumps({"connection": "FAILED", "persistent_writes": 0}))
        return 2
    finally:
        if engine is not None:
            await engine.dispose()


def main() -> int:
    if os.environ.get("DIT_API_RUN_DB_INTEGRATION") != "1":
        print(json.dumps({"connection": "NOT_RUN", "reason": "EXPLICIT_OPT_IN_REQUIRED"}))
        return 2
    return asyncio.run(_run(), loop_factory=new_event_loop)


if __name__ == "__main__":
    raise SystemExit(main())
