"""Local SQLite behavioral checks and MariaDB DDL compilation; NOT live MariaDB evidence."""

import ssl
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import pymysql
import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine, event, select
from sqlalchemy.exc import IntegrityError, StatementError
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.db.models import (
    AcademicMembershipRow,
    AnonymousPostRow,
    AuditLogRow,
    Base,
    DepartmentRow,
    IdentityRow,
    OpportunityCheckItemRow,
    OpportunityRow,
    ProfileRow,
    RecruitmentRow,
    RoleAssignmentRow,
    SavedOpportunityRow,
)
from app.db.schema import initial_schema_sql
from app.db.session import DatabaseSettings, create_database_engine, database_transaction
from app.repositories.p0 import (
    AnonymousPostRepository,
    IdentityRepository,
    SavedOpportunityRepository,
)
from app.schemas.common import ErrorCode
from app.schemas.p0 import VerifiedSubject

NOW = datetime(2026, 10, 30, tzinfo=UTC)


@pytest.fixture
def engine():
    engine = create_engine("sqlite+pysqlite:///:memory:", hide_parameters=True)

    @event.listens_for(engine, "connect")
    def foreign_keys(connection, record):
        connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def session(engine):
    with Session(engine, expire_on_commit=False) as session:
        yield session


def fake_identity(session, subject="student-a", status="active"):
    row = IdentityRow(issuer="https://fake-issuer.invalid", subject=subject, status=status)
    session.add(row)
    session.flush()
    session.add(ProfileRow(user_id=row.id, display_name="가상 사용자"))
    session.flush()
    return row


def fake_opportunity(session):
    row = OpportunityRow(
        kind="공모전",
        title="가상 공고",
        deadline_at=NOW,
        submission_mode="external_link",
    )
    session.add(row)
    session.flush()
    return row


def fake_saved(session, user):
    opportunity = fake_opportunity(session)
    row = SavedOpportunityRow(user_id=user.id, opportunity_id=opportunity.id)
    session.add(row)
    session.flush()
    return row


def test_eleven_logical_tables_have_relations_and_review_only_mariadb_ddl():
    assert set(Base.metadata.tables) == {
        "identities",
        "profiles",
        "departments",
        "academic_memberships",
        "role_assignments",
        "anonymous_posts_private",
        "recruitments",
        "opportunities",
        "saved_opportunities",
        "opportunity_check_items",
        "audit_logs",
    }
    ddl = initial_schema_sql()
    assert ddl.count("CREATE TABLE") == 11
    assert ddl.count("ENGINE=InnoDB") == 11
    assert "binding_digest BINARY(32)" in ddl
    assert "DATETIME(6)" in ddl and "FOREIGN KEY" in ddl and "CHECK" in ddl
    assert all(word not in ddl.upper() for word in ("DROP ", "TRUNCATE ", "GRANT ", "INSERT "))
    snapshot = Path(__file__).parents[1] / "app/db/migrations/0001_initial.review.sql"
    assert snapshot.read_text(encoding="utf-8") == ddl


def test_verified_subject_lookup_is_exact_and_never_creates_identity(session):
    owner = fake_identity(session)
    repo = IdentityRepository(session)
    subject = VerifiedSubject(issuer=owner.issuer, subject=owner.subject)
    assert repo.resolve_verified_subject(subject) == owner.id
    for issuer, value in [(owner.issuer, "STUDENT-A"), (owner.issuer + "/", owner.subject)]:
        assert repo.resolve_verified_subject(VerifiedSubject(issuer=issuer, subject=value)) is None
    assert len(list(session.scalars(select(IdentityRow)))) == 1
    owner.status = "disabled"
    session.flush()
    assert repo.resolve_verified_subject(subject) is None


def test_identity_digest_has_exact_case_sensitive_uniqueness(session):
    first = fake_identity(session, "case")
    second = fake_identity(session, "CASE")
    assert first.binding_digest != second.binding_digest
    session.add(IdentityRow(issuer=first.issuer, subject=first.subject))
    with pytest.raises(IntegrityError):
        session.flush()


def test_primary_membership_is_current_and_fails_closed_on_overlap(session):
    user = fake_identity(session)
    department = DepartmentRow(code="DEMO-A", name="가상 학과")
    session.add(department)
    session.flush()
    first = AcademicMembershipRow(
        user_id=user.id,
        department_id=department.id,
        academic_year=2,
        status="active",
        valid_from=NOW - timedelta(days=1),
        valid_to=NOW + timedelta(days=1),
    )
    session.add(first)
    session.flush()
    repo = IdentityRepository(session)
    assert repo.current_primary_membership(user.id, NOW).id == first.id
    assert repo.current_primary_membership(user.id, NOW + timedelta(days=2)) is None
    session.add(
        AcademicMembershipRow(
            user_id=user.id,
            department_id=department.id,
            academic_year=2,
            status="active",
            valid_from=NOW,
        )
    )
    session.flush()
    assert repo.current_primary_membership(user.id, NOW) is None


def test_scoped_saved_reads_and_revision_updates_reject_other_account(session):
    owner = fake_identity(session)
    other = fake_identity(session, "student-b")
    saved = fake_saved(session, owner)
    mine = SavedOpportunityRepository(session, owner.id)
    theirs = SavedOpportunityRepository(session, other.id)
    with pytest.raises(ApiError) as forbidden:
        theirs.update_memo(saved.id, expected_revision=1, memo="tampered")
    assert forbidden.value.code == ErrorCode.NOT_FOUND
    assert mine.get(saved.id).memo == ""
    mine.update_memo(saved.id, expected_revision=1, memo="가상 준비 메모")
    assert mine.get(saved.id).revision == 2
    with pytest.raises(ApiError) as stale:
        mine.update_memo(saved.id, expected_revision=1, memo="stale overwrite")
    assert stale.value.code == ErrorCode.CONFLICT
    assert mine.get(saved.id).memo == "가상 준비 메모"


def test_check_item_requires_both_parent_and_owner(session):
    owner = fake_identity(session)
    other = fake_identity(session, "student-b")
    saved = fake_saved(session, owner)
    another = fake_saved(session, owner)
    item = OpportunityCheckItemRow(saved_opportunity_id=saved.id, text="가상 준비", sort_order=0)
    session.add(item)
    session.flush()
    assert SavedOpportunityRepository(session, owner.id).get_check(saved.id, item.id).id == item.id
    for actor, parent in [(other.id, saved.id), (owner.id, another.id)]:
        with pytest.raises(ApiError) as failure:
            SavedOpportunityRepository(session, actor).get_check(parent, item.id)
        assert failure.value.code == ErrorCode.NOT_FOUND


def test_anonymous_projection_never_serializes_private_author(session):
    owner = fake_identity(session)
    other = fake_identity(session, "student-b")
    post = AnonymousPostRow(author_id=owner.id, title="가상 게시글", body="가상 내용")
    session.add(post)
    session.flush()
    mine = AnonymousPostRepository(session, owner.id).get_public(post.id)
    public = AnonymousPostRepository(session, other.id).get_public(post.id)
    assert mine.is_mine and not public.is_mine
    assert "author_id" not in public.model_dump()
    assert str(owner.id) not in public.model_dump_json()
    post.status = "hidden"
    session.flush()
    with pytest.raises(ApiError) as hidden:
        AnonymousPostRepository(session, other.id).get_public(post.id)
    assert hidden.value.code == ErrorCode.NOT_FOUND


def test_foreign_key_and_duplicate_saved_constraints(session):
    owner = fake_identity(session)
    saved = fake_saved(session, owner)
    with session.begin_nested(), pytest.raises(IntegrityError):
        session.add(SavedOpportunityRow(user_id=owner.id, opportunity_id=saved.opportunity_id))
        session.flush()
    with session.begin_nested(), pytest.raises(IntegrityError):
        session.add(ProfileRow(user_id=uuid4(), display_name="없는 가상 계정"))
        session.flush()


def test_database_checks_prohibit_invalid_role_capacity_and_anonymous_audit(session):
    owner = fake_identity(session)
    invalid = [
        RoleAssignmentRow(
            user_id=owner.id, role="admin", scope_type="platform", scope_id=uuid4(), valid_from=NOW
        ),
        RecruitmentRow(
            owner_id=owner.id, title="가상 모집", body="가상 설명", capacity=1, deadline_at=NOW
        ),
        AuditLogRow(
            event="post.updated",
            resource_kind="anonymous_post",
            actor_id=owner.id,
            entity_id=uuid4(),
        ),
    ]
    for row in invalid:
        with session.begin_nested(), pytest.raises(IntegrityError):
            session.add(row)
            session.flush()


def test_timestamp_requires_timezone_and_roundtrips_as_utc(session):
    owner = fake_identity(session)
    local = NOW.astimezone(timezone(timedelta(hours=9)))
    row = RecruitmentRow(
        owner_id=owner.id, title="가상 모집", body="가상 설명", capacity=2, deadline_at=local
    )
    session.add(row)
    session.flush()
    session.expire_all()
    assert session.get(RecruitmentRow, row.id).deadline_at == NOW
    with session.begin_nested(), pytest.raises(StatementError):
        session.add(
            RecruitmentRow(
                owner_id=owner.id,
                title="가상 모집",
                body="가상 설명",
                capacity=2,
                deadline_at=NOW.replace(tzinfo=None),
            )
        )
        session.flush()


def test_explicit_transaction_rolls_back(engine):
    with pytest.raises(RuntimeError), database_transaction(engine) as session:
        session.add(DepartmentRow(code="ROLLBACK", name="가상 롤백"))
        session.flush()
        raise RuntimeError("rollback this isolated fixture")
    with Session(engine) as session:
        assert session.scalar(select(DepartmentRow)) is None


def test_database_settings_hide_secret_and_require_explicit_values(monkeypatch):
    with pytest.raises(ValidationError):
        DatabaseSettings()
    secret = "fake-password-for-test-only"
    settings = DatabaseSettings(
        host="fake.invalid", database="fake", username="fake", password=secret
    )
    assert secret not in repr(settings) and secret not in settings.model_dump_json()
    captured = {}

    def disabled_network(*args, **kwargs):
        captured.update(kwargs)
        raise AssertionError("network disabled in test")

    monkeypatch.setattr(pymysql, "connect", disabled_network)
    engine = create_database_engine(settings)
    assert engine.hide_parameters and engine.echo is False
    assert secret not in str(engine.url)
    with pytest.raises(AssertionError, match="network disabled"):
        engine.connect()
    assert captured["ssl"].verify_mode == ssl.CERT_REQUIRED
    assert captured["ssl"].check_hostname is True
    engine.dispose()


@pytest.mark.parametrize("extra", ["email", "role", "user_id", "department_id"])
def test_verified_subject_is_not_a_client_account_binding_request(extra):
    with pytest.raises(ValidationError):
        VerifiedSubject(issuer="fake", subject="fake", **{extra: "injected"})
