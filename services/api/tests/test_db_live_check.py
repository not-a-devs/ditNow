"""Offline verification of the explicit live-check guard; no network or real data."""

import json
from unittest.mock import AsyncMock, Mock

from sqlalchemy import create_engine, text

from app.db import live_check
from app.db.models import Base


def test_without_opt_in_never_reads_settings_or_connects(monkeypatch, capsys):
    monkeypatch.delenv("DIT_API_RUN_DB_INTEGRATION", raising=False)
    settings = Mock(side_effect=AssertionError("must not read settings"))
    monkeypatch.setattr(live_check, "Settings", settings)
    assert live_check.main() == 2
    assert json.loads(capsys.readouterr().out)["connection"] == "NOT_RUN"
    settings.assert_not_called()


def test_opt_in_safe_failure_does_not_print_private_exception(monkeypatch, capsys):
    monkeypatch.setenv("DIT_API_RUN_DB_INTEGRATION", "1")
    monkeypatch.setattr(live_check, "Settings", Mock(return_value=object()))
    engine = Mock(dispose=AsyncMock())
    monkeypatch.setattr(live_check, "create_database_engine", Mock(return_value=engine))
    monkeypatch.setattr(
        live_check,
        "read_only_report",
        AsyncMock(side_effect=RuntimeError("private-host fictional-password")),
    )
    assert live_check.main() == 2
    output = capsys.readouterr().out
    assert "private-host" not in output and "fictional-password" not in output
    assert json.loads(output) == {"connection": "FAILED", "persistent_writes": 0}
    engine.dispose.assert_awaited_once()


def test_schema_readiness_checks_names_only_and_detects_missing_columns():
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        report = live_check.schema_readiness(connection)
        assert report["expected_tables"] == 16
        assert not report["column_names_ready"]
        assert len(report["missing_tables"]) == 16
        connection.execute(text("CREATE TABLE identities (id TEXT)"))
        report = live_check.schema_readiness(connection)
        assert "issuer" in report["missing_columns"]["identities"]
        assert report["record_reads"] == report["persistent_writes"] == 0
    engine.dispose()


def test_matching_schema_does_not_claim_constraints_grants_or_live_crud():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with engine.connect() as connection:
        report = live_check.schema_readiness(connection)
        assert report["column_names_ready"]
        assert report["constraints_and_grants"] == "NOT_RUN"
        assert report["record_reads"] == report["persistent_writes"] == 0
    engine.dispose()
