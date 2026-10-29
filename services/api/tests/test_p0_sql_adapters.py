"""Real SQLAlchemy/SQLite persistence and rollback tests; never MariaDB evidence or live seeds."""

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import event, func, select, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.api.dependencies import VerifiedPrincipal
from app.core.errors import ApiError
from app.db.models import (
    AcademicMembershipRow,
    AnonymousPostPublicRow,
    AnonymousPostRow,
    Base,
    CheckClaimRow,
    CommunityClaimRow,
    DepartmentRow,
    IdentityRow,
    OpportunityCheckItemRow,
    OpportunityRow,
    ProfileRow,
    RecruitmentRow,
    RoleAssignmentRow,
    SavedOpportunityRow,
    SavedStatusEventRow,
)
from app.db.p0_runtime import P0Executor
from app.features.community.schemas import (
    AnonymousPostCreate,
    AnonymousPostUpdate,
    RecruitmentCreate,
    RecruitmentUpdate,
)
from app.features.opportunities.repository import OpportunityQuery
from app.features.opportunities.schemas import (
    CheckItemCreate,
    CheckItemPatch,
    PreparationStatus,
    SavedOpportunityPatch,
    SaveOpportunityRequest,
)
from app.schemas.common import ErrorCode

NOW = datetime(2026, 10, 30, 0, 0, tzinfo=UTC)
OWNER, OTHER, OPP, DEPT = uuid4(), uuid4(), uuid4(), uuid4()


def principal(id=OWNER):
    return VerifiedPrincipal(user_id=id, active=True)


@pytest.fixture
def database(tmp_path):
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{(tmp_path / 'p0.sqlite').as_posix()}",
        poolclass=NullPool,
        hide_parameters=True,
    )

    @event.listens_for(engine.sync_engine, "connect")
    def sqlite_settings(connection, record):
        connection.isolation_level = None
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    @event.listens_for(engine.sync_engine, "begin")
    def sqlite_begin(connection):
        connection.exec_driver_sql("BEGIN")

    async def initialize():
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with async_sessionmaker(engine)() as session, session.begin():
            session.add(DepartmentRow(id=DEPT, code="DEMO", name="가상 학과"))
            for id, label in [(OWNER, "가상 작성자"), (OTHER, "다른 가상 사용자")]:
                session.add(
                    IdentityRow(
                        id=id,
                        issuer="https://fake-issuer.invalid",
                        subject=str(id),
                        status="active",
                        source_kind="DEMO",
                    )
                )
                await session.flush()
                session.add(ProfileRow(user_id=id, display_name=label, source_kind="DEMO"))
                session.add(
                    AcademicMembershipRow(
                        user_id=id,
                        department_id=DEPT,
                        academic_year=2,
                        status="active",
                        valid_from=NOW - timedelta(days=1),
                    )
                )
                session.add(
                    RoleAssignmentRow(
                        user_id=id,
                        role="student",
                        scope_type="platform",
                        status="active",
                        valid_from=NOW - timedelta(days=1),
                    )
                )
            session.add(
                OpportunityRow(
                    id=OPP,
                    kind="contest",
                    title="가상 공모전",
                    organization="가상 기관",
                    eligibility="가상 구성원",
                    status="published",
                    deadline_at=None,
                    submission_mode="external_link",
                    original_url="https://example.test/demo",
                    source_kind="DEMO",
                    target_scope={"level": "school"},
                    files=[],
                )
            )

    asyncio.run(initialize())
    yield engine, P0Executor(engine, clock=lambda: NOW)
    asyncio.run(engine.dispose())


async def scalar(engine, statement):
    async with async_sessionmaker(engine)() as session:
        return await session.scalar(statement)


def test_anonymous_create_replay_cas_delete_and_new_session_persistence(database):
    engine, executor = database

    async def run():
        body = AnonymousPostCreate(title="가상 글", body="지속되는 가상 내용")
        first, replayed = await executor.run(
            principal(), lambda s: s.posts.create(s.actor, body, "same-key")
        )
        second, replayed = await executor.run(
            principal(), lambda s: s.posts.create(s.actor, body, "same-key")
        )
        assert replayed and first.id == second.id
        other = await executor.run(principal(OTHER), lambda s: s.posts.get(s.actor, first.id))
        assert not other.is_mine and "author_id" not in other.model_dump_json()
        assert str(OWNER) not in other.model_dump_json()
        changed = await executor.run(
            principal(),
            lambda s: s.posts.update(
                s.actor, first.id, AnonymousPostUpdate(title="새 가상 제목", revision=1)
            ),
        )
        assert changed.revision == 2
        with pytest.raises(ApiError) as failure:
            await executor.run(
                principal(OTHER),
                lambda s: s.posts.update(
                    s.actor, first.id, AnonymousPostUpdate(title="침입", revision=2)
                ),
            )
        assert failure.value.code == ErrorCode.NOT_FOUND
        with pytest.raises(ApiError) as stale:
            await executor.run(
                principal(),
                lambda s: s.posts.update(
                    s.actor, first.id, AnonymousPostUpdate(title="낡은 변경", revision=1)
                ),
            )
        assert stale.value.code == ErrorCode.CONFLICT
        await executor.run(principal(), lambda s: s.posts.delete(s.actor, first.id, 2))
        with pytest.raises(ApiError):
            await executor.run(principal(), lambda s: s.posts.create(s.actor, body, "same-key"))
        assert await scalar(engine, select(func.count()).select_from(AnonymousPostRow)) == 1
        assert await scalar(engine, select(func.count()).select_from(CommunityClaimRow)) == 1

    asyncio.run(run())


def test_public_reads_do_not_join_private_author_and_claim_keys_are_case_exact(database):
    engine, executor = database
    statements = []

    def trace(conn, cursor, statement, parameters, context, many):
        statements.append(statement)

    event.listen(engine.sync_engine, "before_cursor_execute", trace)

    async def run():
        body = AnonymousPostCreate(title="공개 가상 글", body="가상 내용")
        await executor.run(principal(), lambda s: s.posts.create(s.actor, body, "Case-Key"))
        await executor.run(principal(), lambda s: s.posts.create(s.actor, body, "case-key"))
        page = await executor.run(principal(OTHER), lambda s: s.posts.list(s.actor))
        assert len(page.items) == 2
        public = [sql for sql in statements if "FROM anonymous_posts_public" in sql]
        assert public and all(
            "JOIN anonymous_posts_private" not in sql and "author_id" not in sql for sql in public
        )

    try:
        asyncio.run(run())
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", trace)


def test_public_projection_failure_rolls_back_private_and_claim(database):
    engine, executor = database

    def reject_projection(*args):
        raise RuntimeError("injected projection failure")

    event.listen(AnonymousPostPublicRow, "before_insert", reject_projection)

    async def run():
        with pytest.raises(RuntimeError):
            await executor.run(
                principal(),
                lambda s: s.posts.create(
                    s.actor,
                    AnonymousPostCreate(title="가상 실패", body="가상 내용"),
                    "rollback-key",
                ),
            )
        assert await scalar(engine, select(func.count()).select_from(AnonymousPostRow)) == 0
        assert await scalar(engine, select(func.count()).select_from(CommunityClaimRow)) == 0

    try:
        asyncio.run(run())
    finally:
        event.remove(AnonymousPostPublicRow, "before_insert", reject_projection)


def test_operation_failure_after_successful_create_rolls_back_entire_transaction(database):
    engine, executor = database

    def fail(s):
        s.posts.create(
            s.actor, AnonymousPostCreate(title="가상 롤백", body="가상 내용"), "rollback-all"
        )
        raise RuntimeError("abort outer operation")

    async def run():
        with pytest.raises(RuntimeError):
            await executor.run(principal(), fail)
        assert await scalar(engine, select(func.count()).select_from(CommunityClaimRow)) == 0
        assert await scalar(engine, select(func.count()).select_from(AnonymousPostPublicRow)) == 0

    asyncio.run(run())


def test_current_identity_membership_and_role_revocation_are_rechecked(database):
    engine, executor = database

    async def run():
        await executor.run(principal(), lambda s: s.posts.list(s.actor))
        async with async_sessionmaker(engine)() as session, session.begin():
            await session.execute(
                update(RoleAssignmentRow)
                .where(RoleAssignmentRow.user_id == OWNER)
                .values(status="revoked")
            )
        with pytest.raises(ApiError) as revoked:
            await executor.run(principal(), lambda s: s.posts.list(s.actor))
        assert revoked.value.code == ErrorCode.FORBIDDEN
        async with async_sessionmaker(engine)() as session, session.begin():
            await session.execute(
                update(IdentityRow).where(IdentityRow.id == OWNER).values(status="disabled")
            )
        with pytest.raises(ApiError) as disabled:
            await executor.run_personal(principal(), lambda s: s.list_saved(OWNER))
        assert disabled.value.code == ErrorCode.UNAUTHORIZED

    asyncio.run(run())


def test_saved_records_are_idempotent_owned_and_audited_atomically(database):
    engine, executor = database

    async def run():
        first, created = await executor.run_personal(
            principal(), lambda s: s.save(OWNER, OPP, SaveOpportunityRequest(memo="가상 메모"))
        )
        second, created = await executor.run_personal(
            principal(), lambda s: s.save(OWNER, OPP, SaveOpportunityRequest(memo="다른 재시도"))
        )
        assert not created and second.memo == first.memo
        preparing = await executor.run_personal(
            principal(),
            lambda s: s.update(
                OWNER, OPP, SavedOpportunityPatch(status=PreparationStatus.PREPARING), 1
            ),
        )
        with pytest.raises(ApiError) as other:
            await executor.run_personal(
                principal(OTHER),
                lambda s: s.update(
                    OTHER, OPP, SavedOpportunityPatch(memo="침입"), preparing.revision
                ),
            )
        assert other.value.code == ErrorCode.NOT_FOUND
        assert await scalar(engine, select(func.count()).select_from(SavedStatusEventRow)) == 1
        assert await scalar(engine, select(func.count()).select_from(SavedOpportunityRow)) == 1

    asyncio.run(run())


def test_status_audit_failure_does_not_commit_state_change(database):
    engine, executor = database

    def fail(*args):
        raise RuntimeError("injected status event failure")

    async def run():
        await executor.run_personal(
            principal(), lambda s: s.save(OWNER, OPP, SaveOpportunityRequest())
        )
        event.listen(SavedStatusEventRow, "before_insert", fail)
        try:
            with pytest.raises(RuntimeError):
                await executor.run_personal(
                    principal(),
                    lambda s: s.update(
                        OWNER, OPP, SavedOpportunityPatch(status=PreparationStatus.PREPARING), 1
                    ),
                )
        finally:
            event.remove(SavedStatusEventRow, "before_insert", fail)
        row = (await executor.run_personal(principal(), lambda s: s.list_saved(OWNER)))[0]
        assert row.status is PreparationStatus.INTERESTED and row.revision == 1
        assert await scalar(engine, select(func.count()).select_from(SavedStatusEventRow)) == 0

    asyncio.run(run())


def test_check_replay_sort_conflict_tombstone_and_parent_recreation(database):
    engine, executor = database

    async def run():
        await executor.run_personal(
            principal(), lambda s: s.save(OWNER, OPP, SaveOpportunityRequest())
        )
        body = CheckItemCreate(text="가상 준비", sort_order=0)
        first, created = await executor.run_personal(
            principal(), lambda s: s.add_check(OWNER, OPP, body, "check-key")
        )
        again, created = await executor.run_personal(
            principal(), lambda s: s.add_check(OWNER, OPP, body, "check-key")
        )
        assert not created and first.id == again.id
        with pytest.raises(ApiError):
            await executor.run_personal(
                principal(),
                lambda s: s.add_check(
                    OWNER, OPP, CheckItemCreate(text="중복 순서", sort_order=0), "other-key"
                ),
            )
        await executor.run_personal(principal(), lambda s: s.delete_check(OWNER, OPP, first.id, 1))
        with pytest.raises(ApiError) as replay:
            await executor.run_personal(
                principal(), lambda s: s.add_check(OWNER, OPP, body, "check-key")
            )
        assert replay.value.code == ErrorCode.CONFLICT
        assert await scalar(engine, select(func.count()).select_from(OpportunityCheckItemRow)) == 0
        assert await scalar(engine, select(CheckClaimRow.tombstone)) is True
        await executor.run_personal(principal(), lambda s: s.delete(OWNER, OPP, 1))
        await executor.run_personal(
            principal(), lambda s: s.save(OWNER, OPP, SaveOpportunityRequest())
        )
        with pytest.raises(ApiError):
            await executor.run_personal(
                principal(), lambda s: s.add_check(OWNER, OPP, body, "check-key")
            )

    asyncio.run(run())


def test_check_cas_and_database_sort_order_uniqueness(database):
    engine, executor = database

    async def run():
        await executor.run_personal(
            principal(), lambda s: s.save(OWNER, OPP, SaveOpportunityRequest())
        )
        one, _ = await executor.run_personal(
            principal(),
            lambda s: s.add_check(OWNER, OPP, CheckItemCreate(text="첫 준비", sort_order=0), "one"),
        )
        two, _ = await executor.run_personal(
            principal(),
            lambda s: s.add_check(OWNER, OPP, CheckItemCreate(text="둘 준비", sort_order=1), "two"),
        )
        changed = await executor.run_personal(
            principal(),
            lambda s: s.update_check(OWNER, OPP, one.id, CheckItemPatch(completed=True), 1),
        )
        assert changed.revision == 2 and changed.completed_at == NOW
        with pytest.raises(ApiError):
            await executor.run_personal(
                principal(),
                lambda s: s.update_check(OWNER, OPP, one.id, CheckItemPatch(completed=False), 1),
            )
        with pytest.raises(ApiError):
            await executor.run_personal(
                principal(),
                lambda s: s.update_check(OWNER, OPP, two.id, CheckItemPatch(sort_order=0), 1),
            )

    asyncio.run(run())


def test_recruitment_fields_profiles_and_capacity_revision_guards(database):
    engine, executor = database

    async def run():
        payload = RecruitmentCreate(
            title="가상 팀 모집",
            body="새 협업",
            field="개발",
            roles=["프런트"],
            capacity=4,
            deadline_at=NOW + timedelta(days=2),
            opportunity_id=str(OPP),
        )
        record, _ = await executor.run(
            principal(), lambda s: s.recruitments.create(s.actor, payload, "recruit-key")
        )
        assert record.owner.display_name == "가상 작성자" and record.roles == ["프런트"]
        async with async_sessionmaker(engine)() as session, session.begin():
            await session.execute(
                update(RecruitmentRow)
                .where(RecruitmentRow.id == UUID(record.id))
                .values(accepted_count=2, revision=2)
            )
        with pytest.raises(ApiError) as capacity:
            await executor.run(
                principal(),
                lambda s: s.recruitments.update(
                    s.actor, record.id, RecruitmentUpdate(capacity=2, revision=2)
                ),
            )
        assert capacity.value.code == ErrorCode.CONFLICT

    asyncio.run(run())


def test_public_catalog_allows_no_deadline_and_rejects_invalid_cursor(database):
    engine, executor = database

    async def run():
        page = await executor.public_opportunities(lambda s: s.list_public(OpportunityQuery()))
        assert len(page.items) == 1 and page.items[0].deadline_at is None
        with pytest.raises(ApiError) as error:
            await executor.public_opportunities(
                lambda s: s.list_public(OpportunityQuery(cursor="not-a-uuid"))
            )
        assert error.value.code == ErrorCode.VALIDATION

    asyncio.run(run())


@pytest.mark.parametrize(
    "changes",
    [
        {"target_scope": ["unexpected"]},
        {"target_scope": {"level": "not-supported"}},
        {"target_scope": {"level": "school", "academic_years": ["bad-year"]}},
        {"files": ["unexpected"]},
        {"files": [{"filename": "demo", "checked_at": "2026-10-30T00:00:00"}]},
        {"files": [{"filename": "demo", "checked_at": "not-a-date"}]},
    ],
)
def test_public_catalog_skips_incompatible_json_without_failing_page(database, changes):
    engine, executor = database

    async def run():
        async with async_sessionmaker(engine)() as session, session.begin():
            await session.execute(
                update(OpportunityRow).where(OpportunityRow.id == OPP).values(**changes)
            )
        page = await executor.public_opportunities(lambda s: s.list_public(OpportunityQuery()))
        assert page.items == []
        with pytest.raises(ApiError) as error:
            await executor.public_opportunities(lambda s: s.get_public(OPP))
        assert error.value.code == ErrorCode.NOT_FOUND

    asyncio.run(run())
