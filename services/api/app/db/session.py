"""Explicit MariaDB boundary; never reads credentials or creates schema on import."""

import ssl
from collections.abc import Iterator
from contextlib import contextmanager

from pydantic import BaseModel, ConfigDict, Field, SecretStr
from sqlalchemy import URL, Engine, create_engine
from sqlalchemy.orm import Session


class DatabaseSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True, frozen=True)
    host: str = Field(min_length=1)
    database: str = Field(min_length=1)
    username: str = Field(min_length=1)
    password: SecretStr = Field(min_length=1)
    port: int = Field(default=3306, ge=1, le=65535)

    def connection_url(self) -> URL:
        return URL.create(
            "mariadb+pymysql",
            username=self.username,
            password=self.password.get_secret_value(),
            host=self.host,
            port=self.port,
            database=self.database,
            query={"charset": "utf8mb4"},
        )


def create_database_engine(settings: DatabaseSettings) -> Engine:
    # Network/account provisioning must be approved before connecting. TLS verifies server identity.
    return create_engine(
        settings.connection_url(),
        pool_pre_ping=True,
        hide_parameters=True,
        echo=False,
        connect_args={"connect_timeout": 5, "ssl": ssl.create_default_context()},
    )


@contextmanager
def database_transaction(engine: Engine) -> Iterator[Session]:
    """Caller owns the approved engine; exceptions roll back and the session is always closed."""
    with Session(engine, expire_on_commit=False) as session, session.begin():
        yield session
