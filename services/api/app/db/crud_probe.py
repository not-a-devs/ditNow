"""Opt-in, synthetic rollback-only P0 SQL probe. No routes, DDL, commits or legacy row reads."""

import asyncio
import json
import os
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import event, func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.db_connection import create_database_engine
from app.core.errors import ApiError
from app.core.event_loop import new_event_loop
from app.db.live_check import schema_readiness
from app.db.models import (
    AcademicMembershipRow,
    AnonymousPostPublicRow,
    AnonymousPostRow,
    AuditLogRow,
    Base,
    CheckClaimRow,
    CommunityClaimRow,
    DepartmentRow,
    IdentityRow,
    OpportunityCheckItemRow,
    OpportunityRow,
    ProfileRow,
    RecruitmentApplicationRow,
    RecruitmentRow,
    RoleAssignmentRow,
    SavedOpportunityRow,
    SavedStatusEventRow,
)
from app.features.community.domain import CommunityActor
from app.features.community.schemas import (
    AnonymousPostCreate,
    AnonymousPostUpdate,
    RecruitmentClose,
    RecruitmentCreate,
    RecruitmentUpdate,
)
from app.features.community.service import AnonymousPostService, RecruitmentService
from app.features.opportunities.schemas import (
    CheckItemCreate,
    CheckItemPatch,
    PreparationStatus,
    SavedOpportunityPatch,
    SaveOpportunityRequest,
)
from app.features.opportunities.service import OpportunityService
from app.repositories.community_sql import SQLAnonymousPosts, SQLPublicProfiles, SQLRecruitments
from app.repositories.opportunities_sql import SQLOpportunityCatalog, SQLSavedOpportunities
from app.repositories.p0_access import CurrentP0Access
from app.schemas.common import ErrorCode


class ProbeBlocked(RuntimeError):
    """Static codes only, never raw database/credential/SQL details."""


class IntentionalRollback(Exception):
    pass


def require(value, code="CHECK_FAILED"):
    if not value:
        raise ProbeBlocked(code)


@dataclass
class Fixture:
    owner: UUID = field(default_factory=uuid4)
    other: UUID = field(default_factory=uuid4)
    department: UUID = field(default_factory=uuid4)
    opportunity: UUID = field(default_factory=uuid4)
    resources: set[UUID] = field(default_factory=set)

    @property
    def actors(self):
        return [self.owner, self.other]

    def resource(self):
        value = uuid4()
        self.resources.add(value)
        return value


def fixture_predicates(fixture: Fixture):
    """All 16 tables; each record query is bounded to new fixture UUIDs only."""
    actors, resources = fixture.actors, list(fixture.resources)
    return [
        (IdentityRow, IdentityRow.id.in_(actors)),
        (ProfileRow, ProfileRow.user_id.in_(actors)),
        (DepartmentRow, DepartmentRow.id == fixture.department),
        (AcademicMembershipRow, AcademicMembershipRow.user_id.in_(actors)),
        (RoleAssignmentRow, RoleAssignmentRow.user_id.in_(actors)),
        (OpportunityRow, OpportunityRow.id == fixture.opportunity),
        (
            AnonymousPostRow,
            or_(AnonymousPostRow.author_id.in_(actors), AnonymousPostRow.id.in_(resources)),
        ),
        (AnonymousPostPublicRow, AnonymousPostPublicRow.id.in_(resources)),
        (RecruitmentRow, RecruitmentRow.owner_id.in_(actors)),
        (SavedOpportunityRow, SavedOpportunityRow.user_id.in_(actors)),
        (OpportunityCheckItemRow, OpportunityCheckItemRow.saved_opportunity_id.in_(resources)),
        (CommunityClaimRow, CommunityClaimRow.actor_id.in_(actors)),
        (CheckClaimRow, CheckClaimRow.actor_id.in_(actors)),
        (SavedStatusEventRow, SavedStatusEventRow.user_id.in_(actors)),
        (AuditLogRow, or_(AuditLogRow.actor_id.in_(actors), AuditLogRow.entity_id.in_(resources))),
        (
            RecruitmentApplicationRow,
            or_(
                RecruitmentApplicationRow.applicant_id.in_(actors),
                RecruitmentApplicationRow.recruitment_id.in_(resources),
            ),
        ),
    ]


def fixtures_absent(connection, fixture):
    return all(
        connection.scalar(select(func.count()).select_from(model).where(predicate)) == 0
        for model, predicate in fixture_predicates(fixture)
    )


async def require_preconditions(connection):
    require(connection.dialect.name in {"mysql", "mariadb"}, "MARIADB_REQUIRED")
    version, collation, database = (
        await connection.execute(text("SELECT VERSION(), @@collation_connection, DATABASE()"))
    ).one()
    require(str(version).startswith("11.4.") and "MariaDB" in str(version), "SERVER_VERSION")
    require(collation == "utf8mb4_unicode_ci" and database == "ditnow", "SESSION_CONFIGURATION")
    ready = await connection.run_sync(schema_readiness)
    require(ready["column_names_ready"], "SCHEMA_NOT_READY")
    # DML accounts may not see hidden triggers. Mandatory privileged review attestation is
    # checked BEFORE Settings/network; zero visible triggers does not prove trigger absence.
    tables = sorted(Base.metadata.tables)
    placeholders = ",".join(f":t{i}" for i in range(len(tables)))
    values = {f"t{i}": name for i, name in enumerate(tables)}
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
        len(engines) == 16
        and {row[0] for row in engines} == set(tables)
        and all(str(row[1]).casefold() == "innodb" for row in engines),
        "INNODB_REQUIRED",
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


def create_fixtures(session: Session, fixture: Fixture, now: datetime):
    session.add(
        DepartmentRow(
            id=fixture.department,
            code=f"PROBE_{fixture.department.hex}",
            name="가상 롤백 검사 학과",
        )
    )
    session.flush()
    for user in fixture.actors:
        session.add(
            IdentityRow(
                id=user,
                issuer="urn:ditnow:synthetic:rollback-probe",
                subject=str(user),
                status="active",
                source_kind="DEMO",
            )
        )
        session.flush()
        session.add(
            ProfileRow(user_id=user, display_name="가상 롤백 검사 사용자", source_kind="DEMO")
        )
        session.add(
            AcademicMembershipRow(
                user_id=user,
                department_id=fixture.department,
                academic_year=1,
                status="active",
                valid_from=now - timedelta(minutes=1),
                source_kind="DEMO",
            )
        )
        session.add(
            RoleAssignmentRow(
                user_id=user,
                role="student",
                scope_type="department",
                scope_id=fixture.department,
                status="active",
                valid_from=now - timedelta(minutes=1),
                source_kind="DEMO",
            )
        )
    session.add(
        OpportunityRow(
            id=fixture.opportunity,
            title="가상 롤백 검사 기회",
            kind="contest",
            status="published",
            target_scope={"level": "school"},
            files=[],
            source_kind="DEMO",
            submission_mode="info_only",
            eligibility="가상 데이터만",
            deadline_at=None,
        )
    )
    session.flush()


def expect_denied(code, operation):
    try:
        operation()
    except ApiError as error:
        require(error.code == code)
        return
    raise ProbeBlocked("EXPECTED_DENIAL_MISSING")


def exercise(session: Session, fixture: Fixture, now: datetime):
    def services(user):
        access = CurrentP0Access(session, user, lambda: now)
        access.require(student=True)
        catalog = SQLOpportunityCatalog(session)
        return (
            CommunityActor(str(user), True),
            AnonymousPostService(
                SQLAnonymousPosts(session, access),
                clock=lambda: now,
                id_factory=lambda: str(fixture.resource()),
            ),
            RecruitmentService(
                SQLRecruitments(session, access),
                SQLPublicProfiles(session, access),
                clock=lambda: now,
                id_factory=lambda: str(fixture.resource()),
            ),
            OpportunityService(
                catalog,
                SQLSavedOpportunities(session, access),
                clock=lambda: now,
                id_factory=fixture.resource,
            ),
        )

    owner, posts, recruitments, opportunities = services(fixture.owner)
    other, other_posts, other_recruitments, other_opportunities = services(fixture.other)
    body = AnonymousPostCreate(title="가상 롤백 검사 글", body="개인정보 없는 합성 본문")
    post, replayed = posts.create(owner, body, "probe-post-key")
    require(not replayed)
    again, replayed = posts.create(owner, body, "probe-post-key")
    require(replayed and again.id == post.id)
    public = other_posts.get(other, post.id).model_dump(mode="json")
    require(
        set(public)
        == {
            "id",
            "display_name",
            "title",
            "body",
            "status",
            "comment_count",
            "is_mine",
            "revision",
            "created_at",
            "updated_at",
        }
    )
    require(public["display_name"] == "익명" and not public["is_mine"])
    require(all(str(user) not in json.dumps(public) for user in fixture.actors))
    expect_denied(
        ErrorCode.NOT_FOUND,
        lambda: other_posts.update(
            other, post.id, AnonymousPostUpdate(title="가상 거부", revision=1)
        ),
    )
    updated = posts.update(owner, post.id, AnonymousPostUpdate(title="가상 변경", revision=1))
    require(updated.revision == 2)
    expect_denied(
        ErrorCode.CONFLICT,
        lambda: posts.update(
            owner, post.id, AnonymousPostUpdate(title="가상 낡은 변경", revision=1)
        ),
    )
    posts.delete(owner, post.id, 2)
    expect_denied(ErrorCode.NOT_FOUND, lambda: posts.get(owner, post.id))

    recruitment_body = RecruitmentCreate(
        title="가상 롤백 검사 모집",
        body="가상 협업",
        field="합성 개발",
        roles=["가상 역할"],
        capacity=2,
        deadline_at=now + timedelta(days=1),
    )
    recruitment, _ = recruitments.create(owner, recruitment_body, "probe-recruit-key")
    replay, duplicate = recruitments.create(owner, recruitment_body, "probe-recruit-key")
    require(duplicate and replay.id == recruitment.id)
    require(
        other_recruitments.get(other, recruitment.id).owner.display_name == "가상 롤백 검사 사용자"
    )
    expect_denied(
        ErrorCode.NOT_FOUND,
        lambda: other_recruitments.update(
            other, recruitment.id, RecruitmentUpdate(title="가상 거부", revision=1)
        ),
    )
    changed = recruitments.update(
        owner, recruitment.id, RecruitmentUpdate(title="가상 모집 변경", revision=1)
    )
    require(changed.revision == 2)
    expect_denied(
        ErrorCode.CONFLICT,
        lambda: recruitments.update(
            owner, recruitment.id, RecruitmentUpdate(title="낡은 모집 변경", revision=1)
        ),
    )
    require(
        recruitments.cancel(owner, recruitment.id, RecruitmentClose(revision=2)).status.value
        == "cancelled"
    )

    saved, created = opportunities.save(
        fixture.owner, fixture.opportunity, SaveOpportunityRequest(memo="가상 메모")
    )
    duplicate_saved, duplicate_created = opportunities.save(
        fixture.owner, fixture.opportunity, SaveOpportunityRequest(memo="중복 가상 메모")
    )
    require(created and not duplicate_created and duplicate_saved.memo == saved.memo)
    changed_saved = opportunities.update(
        fixture.owner,
        fixture.opportunity,
        SavedOpportunityPatch(status=PreparationStatus.PREPARING, memo="가상 변경"),
        1,
    )
    require(changed_saved.revision == 2)
    expect_denied(
        ErrorCode.NOT_FOUND,
        lambda: other_opportunities.update(
            fixture.other, fixture.opportunity, SavedOpportunityPatch(memo="가상 거부"), 2
        ),
    )
    expect_denied(
        ErrorCode.CONFLICT,
        lambda: opportunities.update(
            fixture.owner, fixture.opportunity, SavedOpportunityPatch(memo="낡은 변경"), 1
        ),
    )
    check_body = CheckItemCreate(text="가상 준비 항목", sort_order=0)
    check, created = opportunities.add_check(
        fixture.owner, fixture.opportunity, check_body, "probe-check-key"
    )
    replay_check, replay_created = opportunities.add_check(
        fixture.owner, fixture.opportunity, check_body, "probe-check-key"
    )
    require(created and not replay_created and check.id == replay_check.id)
    changed_check = opportunities.update_check(
        fixture.owner, fixture.opportunity, check.id, CheckItemPatch(completed=True), 1
    )
    require(changed_check.revision == 2)
    opportunities.delete_check(fixture.owner, fixture.opportunity, check.id, 2)
    expect_denied(
        ErrorCode.CONFLICT,
        lambda: opportunities.add_check(
            fixture.owner, fixture.opportunity, check_body, "probe-check-key"
        ),
    )
    opportunities.delete(fixture.owner, fixture.opportunity, 2)
    expect_denied(
        ErrorCode.NOT_FOUND,
        lambda: opportunities.update(
            fixture.owner, fixture.opportunity, SavedOpportunityPatch(memo="가상 없음"), 2
        ),
    )

    # Nested adapter savepoints must remain beneath our rollback-only outer transaction.
    failed_id = None
    try:
        with session.begin_nested():
            failed, _ = posts.create(owner, body, "probe-intentional-rollback")
            failed_id = UUID(failed.id)
            raise IntentionalRollback()
    except IntentionalRollback:
        session.expire_all()
    require(failed_id is not None and session.get(AnonymousPostRow, failed_id) is None)
    require(session.get(AnonymousPostPublicRow, failed_id) is None)
    require(
        session.scalar(
            select(func.count())
            .select_from(CommunityClaimRow)
            .where(
                CommunityClaimRow.actor_id == fixture.owner,
                CommunityClaimRow.key == "probe-intentional-rollback",
            )
        )
        == 0
    )
    return {
        "anonymous_crud": "PASS",
        "recruitment_create_read_update_cancel": "PASS",
        "saved_opportunity_crud": "PASS",
        "cross_account_denials": "PASS",
        "anonymous_public_projection": "PASS",
        "cas_and_duplicates": "PASS",
        "nested_rollback": "PASS",
        "http_and_auth": "NOT_RUN",
        "restart_persistence": "NOT_RUN",
    }


@contextmanager
def connection_guards(connection):
    """Scope guards to this checked-out connection; do not alter shared engine listeners."""

    def statement_guard(conn, cursor, statement, parameters, context, many):
        verb = statement.lstrip().split(None, 1)[0].upper() if statement.strip() else ""
        if (
            verb
            not in {
                "SELECT",
                "SHOW",
                "SAVEPOINT",
                "RELEASE",
                "ROLLBACK",
                "INSERT",
                "UPDATE",
                "DELETE",
            }
            or ";" in statement
        ):
            raise ProbeBlocked("STATEMENT_BLOCKED")

    def commit_guard(conn):
        raise ProbeBlocked("COMMIT_BLOCKED")

    event.listen(connection, "before_cursor_execute", statement_guard)
    event.listen(connection, "commit", commit_guard)
    try:
        yield
    finally:
        event.remove(connection, "before_cursor_execute", statement_guard)
        event.remove(connection, "commit", commit_guard)


async def run_probe(engine):
    fixture, now = Fixture(), datetime.now(UTC)
    async with engine.connect() as connection:
        # Connection initialization (the strict factory's SET NAMES) has completed.
        with connection_guards(connection.sync_connection):
            return await _run_on_connection(connection, fixture, now)


async def _run_on_connection(connection, fixture, now):
    await require_preconditions(connection)
    require(await connection.run_sync(fixtures_absent, fixture), "FIXTURE_COLLISION")
    await connection.rollback()  # metadata-only autobegin ends before the explicit test UOW
    transaction = await connection.begin()
    checks, failure = {}, False
    try:
        async with AsyncSession(
            bind=connection,
            autoflush=False,
            expire_on_commit=False,
            join_transaction_mode="rollback_only",
        ) as session:
            await session.run_sync(create_fixtures, fixture, now)
            checks = await session.run_sync(exercise, fixture, now)
    except Exception:
        failure = True
    finally:
        await transaction.rollback()
        # A denied SQLAlchemy commit may have deactivated its transaction wrapper before
        # propagating the event error. Explicitly roll back the DBAPI transaction too.
        await connection.run_sync(lambda conn: conn.connection.rollback())
    # New read transaction after unconditional rollback; never query legacy/personal rows.
    absent = await connection.run_sync(fixtures_absent, fixture)
    await connection.rollback()
    require(absent, "FIXTURE_ABSENCE_NOT_VERIFIED")
    return {
        "status": "FAILED" if failure else "PASS",
        "checks": checks,
        "outer_rollback": "VERIFIED",
        "fixture_absence_next_transaction": "VERIFIED",
        "committed_fixture_rows": 0,
        "legacy_record_reads": 0,
    }


async def _run(settings):
    engine, result = None, None
    try:
        engine = create_database_engine(settings)
        async with asyncio.timeout(60):
            result = await run_probe(engine)
    except Exception:
        result = {"status": "FAILED_OR_BLOCKED", "cleanup": "NOT_VERIFIED"}
    finally:
        if engine is not None:
            try:
                await engine.dispose()
            except Exception:
                result = {"status": "FAILED_OR_BLOCKED", "cleanup": "NOT_VERIFIED"}
    return result


def main():
    if (
        os.environ.get("DIT_API_RUN_CRUD_PROBE") != "1"
        or os.environ.get("DIT_API_CRUD_PROBE_SAFETY_REVIEWED") != "1"
    ):
        print(
            json.dumps(
                {
                    "status": "NOT_RUN",
                    "reason": "EXPLICIT_OPT_IN_AND_PRIVILEGED_TRIGGER_REVIEW_REQUIRED",
                }
            )
        )
        return 2
    try:
        settings = Settings()
        if not settings.database_configured:
            print(json.dumps({"status": "NOT_RUN", "reason": "DATABASE_NOT_CONFIGURED"}))
            return 2
        result = asyncio.run(_run(settings), loop_factory=new_event_loop)
    except Exception:
        result = {"status": "NOT_RUN_OR_FAILED", "cleanup": "NOT_VERIFIED"}
    print(json.dumps(result))
    return 0 if result.get("status") == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
