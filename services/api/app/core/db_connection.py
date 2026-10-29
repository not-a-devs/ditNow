"""Unwired async MariaDB connection factory; no startup connection or DDL.

NFR-SEC-004/005, NFR-PRIV-003, NFR-OPS-001/002. Authentication and GRANT
verification remain separate operational approval gates.
"""

import asyncio
import json
import ssl
from typing import Literal

import aiomysql
from pydantic import BaseModel, ConfigDict
from pymysql.constants import CLIENT
from sqlalchemy import event
from sqlalchemy.engine import URL
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.core.config import Settings

SESSION_CHARSET_SQL = "SET NAMES utf8mb4 COLLATE utf8mb4_unicode_ci"


class DatabaseConfigurationError(RuntimeError):
    """Safe message only: do not attach credentials or driver exceptions."""


class TLSRequiredConnection(aiomysql.Connection):
    """Guard aiomysql 0.3.2's pre-authentication fallback on non-TLS servers.

    This deliberately uses a private hook. Re-review and run the handshake tests
    before changing the pinned driver version. No authentication bytes may be
    sent by the superclass until TLS capability and certificate checks apply.
    """

    async def _request_authentication(self) -> None:
        context = self._ssl_context
        if (
            not isinstance(context, ssl.SSLContext)
            or not context.check_hostname
            or context.verify_mode != ssl.CERT_REQUIRED
            or not self.server_capabilities & CLIENT.SSL
        ):
            raise DatabaseConfigurationError("Verified database TLS is required")
        await super()._request_authentication()


class DatabaseConfigurationReport(BaseModel):
    model_config = ConfigDict(extra="forbid")
    configured: bool
    driver: Literal["sqlalchemy+aiomysql"] = "sqlalchemy+aiomysql"
    expected_server: Literal["MariaDB 11.4"] = "MariaDB 11.4"
    tls_verification: Literal["REQUIRED"] = "REQUIRED"
    connection: Literal["NOT_RUN"] = "NOT_RUN"
    grants: Literal["NOT_RUN"] = "NOT_RUN"
    schema_version: Literal["BLOCKED_LEDGER_CONTRACT"] = "BLOCKED_LEDGER_CONTRACT"


def configuration_report(settings: Settings) -> DatabaseConfigurationReport:
    """Offline diagnostic: no identifiers, network access or secret values."""
    return DatabaseConfigurationReport(configured=settings.database_configured)


def _configure_connection_charset(dbapi_connection, _connection_record) -> None:
    """Run after the dialect's SET NAMES reset; this changes no persisted rows/DDL."""
    try:
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute(SESSION_CHARSET_SQL)
        finally:
            cursor.close()
    except Exception:
        raise DatabaseConfigurationError("Database session initialization failed") from None


def create_database_engine(settings: Settings) -> AsyncEngine:
    """Construct only; the caller must separately approve/open/dispose connections.

    Runtime uses ditnow_app, never a migration account. The factory does not
    establish that the server actually granted only DML: inspect GRANTS before use.
    """
    if not settings.database_configured:
        raise DatabaseConfigurationError("Database is not configured")
    context = ssl.create_default_context(
        cafile=str(settings.db_tls_ca_file) if settings.db_tls_ca_file else None
    )

    async def connect() -> aiomysql.Connection:
        connection = TLSRequiredConnection(
            host=settings.db_host,
            port=settings.db_port,
            user=settings.db_user,
            password=settings.db_password.get_secret_value(),
            db=settings.db_name,
            charset="utf8mb4",
            init_command=SESSION_CHARSET_SQL,
            connect_timeout=settings.db_connect_timeout,
            ssl=context,
            local_infile=False,
            autocommit=False,
            echo=False,
        )
        # aiomysql.connect itself creates Connection then awaits this same method.
        try:
            # Bound the entire TCP/TLS/authentication exchange, not only TCP setup.
            async with asyncio.timeout(settings.db_connect_timeout):
                await connection._connect()
        except Exception:
            connection.close()
            raise DatabaseConfigurationError(
                "Database connection could not be established"
            ) from None
        except BaseException:
            # Caller cancellation must also release a partially opened transport.
            connection.close()
            raise
        return connection

    # Credentials deliberately stay out of the engine URL/repr and exception URL.
    engine = create_async_engine(
        URL.create("mysql+aiomysql"),
        async_creator=connect,
        pool_pre_ping=True,
        hide_parameters=True,
        echo=False,
    )
    # Append after built-in dialect initialization, never insert=True: MySQL's
    # on_connect sets SET NAMES without COLLATE and otherwise resets MariaDB's value.
    event.listen(engine.sync_engine, "connect", _configure_connection_charset)
    return engine


def main() -> int:
    """Print offline status only; never open a connection or print validation input."""
    try:
        report = configuration_report(Settings()).model_dump()
    except (ValueError, OSError):
        report = {"configuration": "INVALID", "connection": "NOT_RUN"}
        print(json.dumps(report))
        return 2
    print(json.dumps(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
