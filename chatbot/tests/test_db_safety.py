"""런타임 DDL 금지·기존 스키마 요구·운영 초기화 거부 회귀 검사."""

import logging
import os
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import event, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import StaticPool

from app.config import Settings
from app.db import DatabaseNotReady, init_db, make_engine, require_existing_schema
from app.main import create_app
from app.schemas import MockData
from tests.conftest import FIXTURES, SQLITE_MEMORY
from tests.test_api import client  # noqa: F401


def test_runtime_auto_init_is_disabled_and_true_is_rejected() -> None:
    assert Settings(_env_file=None).db_auto_init is False
    with pytest.raises(ValidationError, match="DB_AUTO_INIT"):
        Settings(_env_file=None, db_auto_init=True)


def test_settings_secrets_are_hidden_from_repr_and_json() -> None:
    settings = Settings(
        _env_file=None,
        database_url="mysql+aiomysql://fake-user:private-db-password@db.invalid/demo",
        llm_api_key="private-llm-key",
        admin_token="private-admin-token",
    )
    for secret in ["private-db-password", "private-llm-key", "private-admin-token"]:
        assert secret not in repr(settings)
        assert secret not in settings.model_dump_json()


def test_remote_connection_requires_approved_factory_before_network() -> None:
    with pytest.raises(DatabaseNotReady, match="공통 연결 정책") as captured:
        make_engine("mysql+aiomysql://fake-user:private-password@db.invalid/demo")
    assert "private-password" not in str(captured.value)


@pytest.mark.parametrize(
    "suffix", ["?uri=true&mode=rwc", "?uri=true&mode=memory", "?uri=true&cache=shared"]
)
async def test_memory_query_variants_cannot_initialize_or_reset(
    suffix: str, mock_data: MockData
) -> None:
    url = SQLITE_MEMORY + suffix
    with pytest.raises(DatabaseNotReady):
        make_engine(url)
    # 직접 만든 엔진을 전달해도 guard가 연결 전에 거부한다.
    engine = create_async_engine(url, poolclass=StaticPool)
    try:
        with pytest.raises(DatabaseNotReady, match="메모리"):
            await init_db(engine, mock_data, reset=True)
    finally:
        await engine.dispose()


async def test_memory_engine_hides_sql_bindings() -> None:
    engine = make_engine(SQLITE_MEMORY)
    try:
        assert engine.sync_engine.hide_parameters is True
    finally:
        await engine.dispose()


async def test_injected_factory_must_hide_parameters() -> None:
    engine = create_async_engine(SQLITE_MEMORY)
    try:
        with pytest.raises(DatabaseNotReady):
            make_engine(
                "mysql+aiomysql://fake-user:private-password@db.invalid/demo",
                approved_factory=lambda _secret: engine,
            )
    finally:
        await engine.dispose()


def test_factory_exception_does_not_expose_dsn() -> None:
    def broken_factory(_secret):
        raise ValueError("private-driver-password")

    with pytest.raises(DatabaseNotReady) as captured:
        make_engine(
            "mysql+aiomysql://fake-user:private-password@db.invalid/demo",
            approved_factory=broken_factory,
        )
    assert "private-driver-password" not in str(captured.value)


async def test_schema_check_never_creates_missing_tables() -> None:
    engine = make_engine(SQLITE_MEMORY)
    statements: list[str] = []
    event.listen(
        engine.sync_engine, "before_cursor_execute", lambda _c, _cu, sql, *_: statements.append(sql)
    )
    try:
        with pytest.raises(DatabaseNotReady, match="스키마"):
            await require_existing_schema(engine)
        assert not any(
            sql.lstrip().upper().startswith(("CREATE", "DROP", "INSERT")) for sql in statements
        )
    finally:
        await engine.dispose()


async def test_existing_data_survives_read_only_schema_check(mock_data: MockData) -> None:
    engine = make_engine(SQLITE_MEMORY)
    try:
        await init_db(engine, mock_data)
        async with engine.begin() as connection:
            await connection.execute(
                text("UPDATE students SET name='preserved-demo' WHERE student_id='20231001'")
            )
        await require_existing_schema(engine)
        async with engine.connect() as connection:
            assert (
                await connection.scalar(
                    text("SELECT name FROM students WHERE student_id='20231001'")
                )
                == "preserved-demo"
            )
    finally:
        await engine.dispose()


async def test_reset_rejects_persistent_targets_before_connecting(
    tmp_path: Path, mock_data: MockData
) -> None:
    database = tmp_path / "must-not-exist.sqlite"
    engine = create_async_engine(f"sqlite+aiosqlite:///{database.as_posix()}")
    try:
        with pytest.raises(DatabaseNotReady, match="메모리"):
            await init_db(engine, mock_data, reset=True)
        assert not database.exists()
    finally:
        await engine.dispose()


def test_missing_schema_fails_startup_without_provisioning(monkeypatch: pytest.MonkeyPatch) -> None:
    engine = make_engine(SQLITE_MEMORY)
    monkeypatch.setattr("app.main.make_engine", lambda _url, **_options: engine)
    settings = Settings(
        _env_file=None, data_dir=FIXTURES, database_url=SQLITE_MEMORY, llm_provider="fake"
    )
    with pytest.raises(DatabaseNotReady, match="스키마"):
        with TestClient(create_app(settings)):
            pytest.fail("Missing schema must not start a legacy runtime")


def test_legacy_seed_reset_cli_is_rejected_without_loading_credentials() -> None:
    env = dict(
        os.environ,
        DATABASE_URL="mysql+aiomysql://private-user:private-password@db.invalid/demo",
        DB_AUTO_INIT="false",
    )
    result = subprocess.run(
        [sys.executable, "scripts/seed_db.py", "--reset"],
        cwd=Path(__file__).resolve().parents[1],
        env=env,
        capture_output=True,
    )
    assert result.returncode == 2
    assert b"private-password" not in result.stdout + result.stderr


def test_seed_command_rejects_remote_database_without_network() -> None:
    env = dict(
        os.environ,
        DATABASE_URL="mysql+aiomysql://private-user:private-password@db.invalid/demo",
        DB_AUTO_INIT="false",
    )
    result = subprocess.run(
        [sys.executable, "scripts/seed_db.py", "--confirm-ephemeral-test"],
        cwd=Path(__file__).resolve().parents[1],
        env=env,
        capture_output=True,
    )
    assert result.returncode == 2
    assert b"private-password" not in result.stdout + result.stderr


def test_db_logging_does_not_include_sql_bindings(
    client: TestClient,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    # 별도 시연의 질문 감사 저장 오류도 질문/DSN 예외를 로그에 남기지 않는다.
    async def broken_commit(_session: AsyncSession) -> None:
        raise OperationalError("private-question", {}, Exception("private-password"))

    monkeypatch.setattr(AsyncSession, "commit", broken_commit)
    with caplog.at_level(logging.WARNING, logger="app.main"):
        response = client.post("/ask", json={"question": "학식"})
    assert response.status_code == 200
    assert "질문 로그 저장 실패" in caplog.text
    assert "private-question" not in caplog.text
    assert "private-password" not in caplog.text
