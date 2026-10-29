"""Fake common-ledger tests and real existing token authority on isolated SQLite only."""

import asyncio
from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from pydantic import SecretStr, ValidationError

from app.core.errors import ApiError
from app.integrations.identity_bridge.contracts import (
    ApprovedMapping,
    BridgePrincipal,
    CurrentIdentity,
    CurrentMembership,
    CurrentProfile,
    CurrentRole,
)
from app.integrations.identity_bridge.legacy import ExistingLegacyTokenVerifier
from app.integrations.identity_bridge.service import IdentityBridge, get_identity_bridge
from app.schemas.common import ErrorCode

NOW = datetime(2026, 10, 30, 12, tzinfo=UTC)
USER = UUID(int=1)
OTHER = UUID(int=2)
DEPT = UUID(int=3)
ISSUER = "urn:ditnow:legacy:demo-students"
SUBJECT = "DEMO-001"
TOKEN = SecretStr("only-a-fictional-test-token")


class Verifier:
    def __init__(self):
        self.subject = SUBJECT
        self.calls = 0

    async def verify(self, token):
        self.calls += 1
        assert isinstance(token, SecretStr)
        return self.subject


class Ledger:
    def __init__(self):
        mapping = ApprovedMapping(ISSUER, SUBJECT, USER, OTHER, NOW, "DEMO")
        self.mappings = [mapping]
        self.reverse = [mapping]
        self.ident = CurrentIdentity(USER, ISSUER, SUBJECT, "active", "DEMO")
        self.prof = CurrentProfile(USER, "DEMO")
        self.members = [CurrentMembership(USER, DEPT, 1, "active", NOW)]
        self.grants = [CurrentRole(USER, "student", "department", DEPT, "active", NOW)]
        self.transactions = 0

    @asynccontextmanager
    async def transaction(self):
        self.transactions += 1
        yield self

    async def mappings_for_subject(self, issuer, subject):
        assert issuer == ISSUER
        return self.mappings

    async def mappings_for_user(self, user_id):
        return self.reverse

    async def identity(self, user_id):
        return self.ident

    async def profile(self, user_id):
        return self.prof

    async def memberships(self, user_id):
        return self.members

    async def roles(self, user_id):
        return self.grants


def configured():
    verifier, ledger = Verifier(), Ledger()
    bridge = IdentityBridge(issuer=ISSUER, verifier=verifier, ledger=ledger, clock=lambda: NOW)
    return bridge, verifier, ledger


def denied(bridge, code=ErrorCode.FORBIDDEN, token=TOKEN):
    with pytest.raises(ApiError) as exc:
        asyncio.run(bridge.resolve_student(token))
    assert exc.value.code == code
    assert SUBJECT not in str(exc.value)
    assert TOKEN.get_secret_value() not in str(exc.value)


def test_approved_current_student_returns_minimal_frozen_internal_principal(caplog):
    bridge, verifier, ledger = configured()
    principal = asyncio.run(bridge.resolve_student(TOKEN))
    assert principal.model_dump(mode="json") == {"user_id": str(USER), "active": True}
    assert verifier.calls == ledger.transactions == 1
    assert caplog.text == ""
    with pytest.raises(ValidationError):
        principal.active = False
    with pytest.raises(ValidationError):
        BridgePrincipal(user_id=USER, active=True, student_id=SUBJECT)
    assert SUBJECT not in repr(ledger.mappings[0])


@pytest.mark.parametrize("field,value", [("issuer", None), ("verifier", None), ("ledger", None)])
def test_partial_configuration_fails_closed(field, value):
    args = {"issuer": ISSUER, "verifier": Verifier(), "ledger": Ledger()}
    args[field] = value
    denied(IdentityBridge(**args), ErrorCode.UNAVAILABLE)


def test_default_dependency_is_unavailable():
    denied(IdentityBridge(), ErrorCode.UNAVAILABLE)
    with pytest.raises(ApiError) as exc:
        get_identity_bridge()
    assert exc.value.code == ErrorCode.UNAVAILABLE


@pytest.mark.parametrize("token", ["", "x" * 513, "bearer token", "token\r\n"])
def test_bad_token_is_rejected_before_verification(token):
    bridge, verifier, ledger = configured()
    denied(bridge, ErrorCode.UNAUTHORIZED, SecretStr(token))
    assert verifier.calls == ledger.transactions == 0


@pytest.mark.parametrize("subject", [None, "", "x" * 21])
def test_invalid_or_expired_authority_result(subject):
    bridge, verifier, ledger = configured()
    verifier.subject = subject
    denied(bridge, ErrorCode.UNAUTHORIZED)
    assert ledger.transactions == 0


@pytest.mark.parametrize(
    "change",
    [
        {"active": False},
        {"active": 1},
        {"approved_by": None},
        {"approved_by": str(OTHER)},
        {"approved_by": UUID(int=0)},
        {"user_id": None},
        {"user_id": str(USER)},
        {"user_id": UUID(int=0)},
        {"revoked_at": NOW},
        {"legacy_source_kind": "UNKNOWN"},
        {"approved_at": NOW + timedelta(seconds=1)},
        {"approved_at": NOW.replace(tzinfo=None)},
        {"subject": SUBJECT.lower()},
        {"issuer": ISSUER.upper()},
    ],
)
def test_approval_status_provenance_and_exact_subject(change):
    bridge, _, ledger = configured()
    ledger.mappings = ledger.reverse = [replace(ledger.mappings[0], **change)]
    denied(bridge)


@pytest.mark.parametrize("scenario", ["missing", "duplicate", "alias", "reverse-mismatch"])
def test_missing_collision_and_many_subjects_to_one_user(scenario):
    bridge, _, ledger = configured()
    if scenario == "missing":
        ledger.mappings = []
    elif scenario == "duplicate":
        ledger.mappings *= 2
    elif scenario == "alias":
        ledger.reverse += [replace(ledger.mappings[0], subject="different-student")]
    else:
        ledger.reverse = [replace(ledger.mappings[0], user_id=OTHER)]
    denied(bridge)


@pytest.mark.parametrize(
    "field,change",
    [
        ("ident", {"status": "disabled"}),
        ("ident", {"user_id": OTHER}),
        ("ident", {"subject": "different-student"}),
        ("ident", {"issuer": "different-issuer"}),
        ("ident", {"source_kind": "OFFICIAL"}),
        ("prof", {"user_id": OTHER}),
        ("prof", {"source_kind": "UNKNOWN"}),
    ],
)
def test_current_identity_profile_cannot_be_inferred_from_legacy(field, change):
    bridge, _, ledger = configured()
    setattr(ledger, field, replace(getattr(ledger, field), **change))
    denied(bridge)


@pytest.mark.parametrize("field", ["ident", "prof"])
def test_missing_common_identity_or_profile(field):
    bridge, _, ledger = configured()
    setattr(ledger, field, None)
    denied(bridge)


@pytest.mark.parametrize(
    "change",
    [
        {"status": "inactive"},
        {"user_id": OTHER},
        {"academic_year": 0},
        {"academic_year": True},
        {"department_id": UUID(int=0)},
        {"department_id": str(DEPT)},
        {"valid_from": NOW + timedelta(seconds=1)},
        {"valid_to": NOW},
        {"valid_from": NOW.replace(tzinfo=None)},
    ],
)
def test_current_membership_not_old_token_grade(change):
    bridge, _, ledger = configured()
    ledger.members = [replace(ledger.members[0], **change)]
    denied(bridge)


def test_ambiguous_memberships_denied():
    bridge, _, ledger = configured()
    ledger.members *= 2
    denied(bridge)


@pytest.mark.parametrize(
    "change",
    [
        {"role": "admin"},
        {"user_id": OTHER},
        {"scope_id": OTHER},
        {"scope_type": "platform", "scope_id": DEPT},
        {"status": "revoked"},
        {"valid_to": NOW},
        {"valid_from": NOW + timedelta(seconds=1)},
    ],
)
def test_current_student_role_scope_and_period(change):
    bridge, _, ledger = configured()
    ledger.grants = [replace(ledger.grants[0], **change)]
    denied(bridge)


def test_platform_student_allowed_but_department_change_rechecked_on_each_call():
    bridge, verifier, ledger = configured()
    assert asyncio.run(bridge.resolve_student(TOKEN)).user_id == USER
    ledger.members = [replace(ledger.members[0], department_id=OTHER)]
    denied(bridge)
    ledger.grants = [replace(ledger.grants[0], scope_type="platform", scope_id=None)]
    assert asyncio.run(bridge.resolve_student(TOKEN)).user_id == USER
    ledger.grants = []
    denied(bridge)
    assert verifier.calls == ledger.transactions == 4


def test_revoked_token_and_changed_subject_not_cached():
    bridge, verifier, ledger = configured()
    asyncio.run(bridge.resolve_student(TOKEN))
    verifier.subject = "changed-subject"
    denied(bridge)
    verifier.subject = None
    denied(bridge, ErrorCode.UNAUTHORIZED)
    assert verifier.calls == 3
    assert ledger.transactions == 2


def test_driver_failure_is_sanitized_without_logging(caplog):
    class BrokenVerifier:
        async def verify(self, token):
            raise RuntimeError(f"secret={token.get_secret_value()} subject={SUBJECT}")

    denied(
        IdentityBridge(issuer=ISSUER, verifier=BrokenVerifier(), ledger=Ledger()),
        ErrorCode.UNAVAILABLE,
    )
    assert caplog.text == ""


def test_naive_clock_unavailable():
    bridge, _, _ = configured()
    bridge._clock = lambda: NOW.replace(tzinfo=None)
    denied(bridge, ErrorCode.UNAVAILABLE)


def test_existing_legacy_authority_reused_with_fresh_sessions_and_revocation(tmp_path):
    from chatbot.app.auth import issue_token, now_utc, revoke_token
    from chatbot.app.models import AuthSessionRow, StudentRow
    from sqlalchemy import update
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    async def scenario():
        engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'fictional.sqlite'}")
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with engine.begin() as connection:
                await connection.run_sync(StudentRow.__table__.create)
                await connection.run_sync(AuthSessionRow.__table__.create)
            async with sessions() as db:
                db.add(
                    StudentRow(
                        student_id=SUBJECT,
                        name="가상",
                        dept_id="fictional",
                        grade=1,
                        password_hash="unused-fictional-no-login",
                    )
                )
                await db.commit()
                token = await issue_token(db, SUBJECT)
            verifier = ExistingLegacyTokenVerifier(sessions)
            assert await verifier.verify(SecretStr(token)) == SUBJECT
            async with sessions() as db:
                await revoke_token(db, token)
            assert await verifier.verify(SecretStr(token)) is None
            async with sessions() as db:
                token = await issue_token(db, SUBJECT)
                await db.execute(
                    update(AuthSessionRow).values(expires_at=now_utc() - timedelta(seconds=1))
                )
                await db.commit()
            assert await verifier.verify(SecretStr(token)) is None
            assert await verifier.verify(SecretStr("not-a-session")) is None
        finally:
            await engine.dispose()

    asyncio.run(scenario())
