"""Full HTTP/SQLAlchemy/SQLite sessions. No MariaDB, real credentials or production seeding."""

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from chatbot.app.auth import _token_hash, hash_password, issue_token
from chatbot.app.models import AuthSessionRow, StudentRow
from chatbot.app.models import Base as LoginBase
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import delete, event, func, select, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import Settings
from app.core.errors import ApiError
from app.db.models import (
    AcademicMembershipRow,
    AnonymousPostPublicRow,
    AnonymousPostRow,
    AuditLogRow,
    Base,
    CommunityClaimRow,
    DepartmentRow,
    IdentityRow,
    OpportunityRow,
    ProfileRow,
    RecruitmentRow,
    RoleAssignmentRow,
)
from app.factory import create_app
from app.integrations.platform_runtime.bindings import LOGIN_ISSUER
from app.integrations.platform_runtime.runtime import PlatformRuntime

PASSWORD = "synthetic-test-password"


@pytest.fixture
def platform(tmp_path, monkeypatch):
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'platform.sqlite'}",
        poolclass=NullPool,
        hide_parameters=True,
    )

    @event.listens_for(engine.sync_engine, "connect")
    def setup(connection, _):
        connection.isolation_level = None
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    @event.listens_for(engine.sync_engine, "begin")
    def begin(connection):
        connection.exec_driver_sql("BEGIN")

    ids = {
        name: uuid4()
        for name in (
            "owner",
            "other",
            "operator",
            "dept",
            "approval_a",
            "approval_b",
            "opportunity",
        )
    }
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    now = datetime.now(UTC)

    async def initialize():
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
            await connection.run_sync(LoginBase.metadata.create_all)
        async with sessions() as db, db.begin():
            db.add(DepartmentRow(id=ids["dept"], code="DEMO_DEPT", name="가상 학과"))
            db.add(
                IdentityRow(
                    id=ids["operator"],
                    issuer="urn:ditnow:operator:demo:v1",
                    subject="synthetic-operator",
                    status="disabled",
                    source_kind="DEMO",
                )
            )
            for who, subject in (("owner", "DITDEMO_A"), ("other", "DITDEMO_B")):
                db.add(
                    IdentityRow(
                        id=ids[who],
                        issuer=LOGIN_ISSUER,
                        subject=subject,
                        status="active",
                        source_kind="DEMO",
                    )
                )
                db.add(
                    StudentRow(
                        student_id=subject,
                        name="구형 가상 이름",
                        dept_id="OLD_DEPT",
                        grade=9,
                        password_hash=hash_password(PASSWORD),
                    )
                )
            await db.flush()
            for who, approval in (("owner", "approval_a"), ("other", "approval_b")):
                db.add(ProfileRow(user_id=ids[who], display_name=f"가상 {who}", source_kind="DEMO"))
                db.add(
                    AcademicMembershipRow(
                        user_id=ids[who],
                        department_id=ids["dept"],
                        academic_year=2,
                        status="active",
                        valid_from=now - timedelta(days=1),
                        source_kind="DEMO",
                    )
                )
                db.add(
                    RoleAssignmentRow(
                        user_id=ids[who],
                        role="student",
                        scope_type="department",
                        scope_id=ids["dept"],
                        status="active",
                        valid_from=now - timedelta(days=1),
                        source_kind="DEMO",
                    )
                )
                db.add(
                    AuditLogRow(
                        id=ids[approval],
                        event="identity_binding_approved",
                        resource_kind="identity_binding",
                        actor_id=ids["operator"],
                        entity_id=ids[who],
                        source_kind="DEMO",
                    )
                )
            db.add(
                OpportunityRow(
                    id=ids["opportunity"],
                    kind="contest",
                    title="가상 준비 공고",
                    status="published",
                    source_kind="DEMO",
                    submission_mode="external_link",
                    target_scope={"level": "school"},
                    files=[],
                )
            )

    asyncio.run(initialize())
    monkeypatch.setattr("app.factory.create_database_engine", lambda _: engine)

    async def schema_report(_):
        return {
            key: True
            for key in (
                "expected_mariadb_11_4",
                "expected_connection_collation",
                "expected_schema",
                "column_names_ready",
            )
        }

    monkeypatch.setattr("app.integrations.platform_runtime.runtime.read_only_report", schema_report)
    app = create_app(
        Settings(
            environment="test",
            p0_runtime_enabled=True,
            p0_schema_approved=True,
            p0_identity_approval_ids=[ids["approval_a"], ids["approval_b"]],
            db_host="synthetic.invalid",
            db_user="ditnow_app",
            db_password=SecretStr("synthetic-only"),
            ask_rate_limit_per_min=1000,
            cors_origins=["http://localhost:5173"],
        )
    )

    def execute(operation):
        async def run():
            async with sessions() as db, db.begin():
                return await operation(db)

        return asyncio.run(run())

    yield app, ids, engine, execute
    asyncio.run(engine.dispose())


def login(client, subject="DITDEMO_A"):
    response = client.post("/api/v1/auth/login", json={"student_id": subject, "password": PASSWORD})
    assert response.status_code == 200, response.text
    assert response.json()["data"]["record_source"] == "DEMO"
    return {"Authorization": "Bearer " + response.json()["data"]["token"]}


def test_default_and_partial_opt_in_fail_closed_without_engine(monkeypatch):
    def forbidden(_):
        raise AssertionError("engine must not be built")

    monkeypatch.setattr("app.factory.create_database_engine", forbidden)
    for enabled in (False, True):
        app = create_app(Settings(environment="test", p0_runtime_enabled=enabled))
        with TestClient(app) as client:
            assert client.get("/api/v1/auth/me").status_code == 503
            assert (
                client.post(
                    "/api/v1/auth/login", json={"student_id": "X", "password": "X"}
                ).status_code
                == 503
            )
            if enabled:
                response = client.get("/api/v1/anonymous-posts")
                assert response.status_code == 503
                assert response.headers["cache-control"] == "private, no-store"


def test_login_me_fresh_session_and_single_shared_engine(platform):
    app, ids, engine, _ = platform
    assert app.state.assistant.engine is engine is app.state.platform_runtime.engine
    with TestClient(app) as client:
        headers = login(client)
        response = client.get("/api/v1/auth/me", headers=headers)
        assert response.status_code == 200
        assert response.json()["data"] == {
            "user_id": str(ids["owner"]),
            "display_name": "가상 owner",
            "record_source": "DEMO",
            "department_id": str(ids["dept"]),
            "department_code": "DEMO_DEPT",
            "academic_year": 2,
            "community_access": True,
        }
        # Canonical department/year is authoritative; stale legacy copies do not deny login.
        assert response.headers["cache-control"] == "private, no-store"
        assert client.get("/api/v1/auth/me").status_code == 401
        assert client.post("/api/v1/auth/logout", headers=headers).status_code == 200
        assert client.get("/api/v1/auth/me", headers=headers).status_code == 401


def test_anonymous_http_crud_replay_cas_privacy_and_fresh_read(platform, caplog):
    app, ids, _, _ = platform
    with TestClient(app) as client:
        owner, other = login(client), login(client, "DITDEMO_B")
        headers = {**owner, "Idempotency-Key": "post-intent-01"}
        payload = {"title": "가상 익명 글", "body": "민감 정보 없는 합성 내용"}
        first = client.post("/api/v1/anonymous-posts", headers=headers, json=payload)
        assert first.status_code == 201
        post = first.json()["data"]
        id = post["id"]
        replay = client.post("/api/v1/anonymous-posts", headers=headers, json=payload)
        assert replay.headers["Idempotent-Replayed"] == "true" and replay.json()["data"]["id"] == id
        visible = client.get(f"/api/v1/anonymous-posts/{id}", headers=other)
        assert visible.status_code == 200 and not visible.json()["data"]["is_mine"]
        assert (
            not {"author_id", "user_id", "department_id", "owner"} & visible.json()["data"].keys()
        )
        assert str(ids["owner"]) not in visible.text
        assert (
            client.patch(
                f"/api/v1/anonymous-posts/{id}",
                headers=other,
                json={"title": "타인 변경", "revision": 1},
            ).status_code
            == 404
        )
        changed = client.patch(
            f"/api/v1/anonymous-posts/{id}",
            headers=owner,
            json={"title": "가상 수정 글", "revision": 1},
        )
        assert changed.status_code == 200 and changed.json()["data"]["revision"] == 2
        assert (
            client.patch(
                f"/api/v1/anonymous-posts/{id}",
                headers=owner,
                json={"title": "낡은 수정", "revision": 1},
            ).status_code
            == 409
        )
        assert (
            client.get(f"/api/v1/anonymous-posts/{id}", headers=other).json()["data"]["title"]
            == "가상 수정 글"
        )
        assert (
            client.delete(f"/api/v1/anonymous-posts/{id}?revision=2", headers=owner).status_code
            == 200
        )
        assert client.get(f"/api/v1/anonymous-posts/{id}", headers=owner).status_code == 404
        assert (
            client.post("/api/v1/anonymous-posts", headers=headers, json=payload).status_code == 404
        )
        assert owner["Authorization"] not in caplog.text
        assert payload["body"] not in caplog.text


def recruitment_body():
    return {
        "title": "가상 모집",
        "body": "가상 협업",
        "field": "개발",
        "roles": ["가상 역할"],
        "capacity": 2,
        "deadline_at": (datetime.now(UTC) + timedelta(days=1)).isoformat(),
    }


def test_recruitment_crud_cancel_tombstone_not_close(platform):
    app, ids, _, execute = platform
    with TestClient(app) as client:
        owner, other = login(client), login(client, "DITDEMO_B")
        headers = {**owner, "Idempotency-Key": "recruit-intent-01"}
        body = recruitment_body()
        created = client.post("/api/v1/recruitments", headers=headers, json=body)
        assert created.status_code == 201
        id = created.json()["data"]["id"]
        assert created.json()["data"]["owner"] == {"display_name": "가상 owner"}
        assert (
            client.delete(f"/api/v1/recruitments/{id}?revision=1", headers=other).status_code == 404
        )
        assert (
            client.patch(
                f"/api/v1/recruitments/{id}",
                headers=owner,
                json={"revision": 1, "title": "가상 모집 수정"},
            ).status_code
            == 200
        )
        assert (
            client.delete(f"/api/v1/recruitments/{id}?revision=1", headers=owner).status_code == 409
        )
        assert client.delete(f"/api/v1/recruitments/{id}?revision=2", headers=owner).json()[
            "data"
        ] == {"id": id, "deleted": True}
        for actor in (owner, other):
            assert client.get(f"/api/v1/recruitments/{id}", headers=actor).status_code == 404
            assert not client.get("/api/v1/recruitments", headers=actor).json()["data"]["items"]
        assert (
            client.delete(f"/api/v1/recruitments/{id}?revision=2", headers=owner).status_code == 404
        )
        assert client.post("/api/v1/recruitments", headers=headers, json=body).status_code == 404
        closed = client.post(
            "/api/v1/recruitments",
            headers={**owner, "Idempotency-Key": "different-intent"},
            json=body,
        ).json()["data"]["id"]
        assert (
            client.post(
                f"/api/v1/recruitments/{closed}/close", headers=owner, json={"revision": 1}
            ).json()["data"]["status"]
            == "closed"
        )
        assert (
            client.delete(f"/api/v1/recruitments/{closed}?revision=2", headers=owner).status_code
            == 409
        )

    async def retained(db):
        row = await db.get(RecruitmentRow, __import__("uuid").UUID(id))
        assert row.status == "cancelled"
        assert await db.scalar(select(func.count()).select_from(CommunityClaimRow)) == 2

    execute(retained)


def test_personal_opportunity_and_checklist_http_crud_with_strong_cas(platform):
    app, ids, _, _ = platform
    with TestClient(app) as client:
        owner, other = login(client), login(client, "DITDEMO_B")
        id = ids["opportunity"]
        path = f"/api/v1/me/saved-opportunities/{id}"
        assert client.get("/api/v1/opportunities").json()["data"]["items"]
        assert client.put(path, headers=owner, json={"memo": "가상 메모"}).status_code == 201
        assert client.put(path, headers=owner, json={"memo": "덮어쓰지 않음"}).status_code == 200
        assert not client.get("/api/v1/me/saved-opportunities", headers=other).json()["data"][
            "items"
        ]
        assert (
            client.patch(
                path, headers={**other, "If-Match": '"1"'}, json={"memo": "타인"}
            ).status_code
            == 404
        )
        assert (
            client.patch(
                path, headers={**owner, "If-Match": 'W/"1"'}, json={"memo": "약한 태그"}
            ).status_code
            == 400
        )
        assert (
            client.patch(
                path, headers={**owner, "If-Match": '"1"'}, json={"status": "preparing"}
            ).status_code
            == 200
        )
        assert (
            client.patch(
                path, headers={**owner, "If-Match": '"1"'}, json={"memo": "낡은 수정"}
            ).status_code
            == 409
        )
        key = {**owner, "Idempotency-Key": "check-intent-01"}
        payload = {"text": "가상 준비", "sort_order": 0}
        check = client.post(path + "/checks", headers=key, json=payload)
        assert check.status_code == 201
        check_id = check.json()["data"]["id"]
        assert client.post(path + "/checks", headers=key, json=payload).status_code == 200
        check_path = path + "/checks/" + check_id
        assert (
            client.patch(
                check_path, headers={**other, "If-Match": '"1"'}, json={"completed": True}
            ).status_code
            == 404
        )
        assert (
            client.patch(
                check_path, headers={**owner, "If-Match": '"1"'}, json={"completed": True}
            ).status_code
            == 200
        )
        assert client.delete(check_path, headers={**owner, "If-Match": '"2"'}).status_code == 200
        assert client.post(path + "/checks", headers=key, json=payload).status_code == 409
        assert client.delete(path, headers={**owner, "If-Match": '"2"'}).status_code == 200
        assert not client.get("/api/v1/me/saved-opportunities", headers=owner).json()["data"][
            "items"
        ]


@pytest.mark.parametrize(
    "mutation",
    [
        "binding",
        "operator",
        "operator_role",
        "profile",
        "membership",
        "role",
        "scope",
        "identity",
        "source",
    ],
)
def test_unapproved_or_revoked_current_binding_denies_next_request(platform, mutation):
    app, ids, _, execute = platform
    with TestClient(app) as client:
        headers = login(client)

        async def revoke(db):
            if mutation == "binding":
                await db.execute(
                    update(AuditLogRow)
                    .where(AuditLogRow.id == ids["approval_a"])
                    .values(event="revoked")
                )
            elif mutation == "operator":
                await db.execute(
                    update(AuditLogRow)
                    .where(AuditLogRow.id == ids["approval_a"])
                    .values(actor_id=None)
                )
            elif mutation == "operator_role":
                db.add(
                    RoleAssignmentRow(
                        user_id=ids["operator"],
                        role="student",
                        scope_type="platform",
                        scope_id=None,
                        status="revoked",
                        valid_from=datetime.now(UTC),
                    )
                )
            elif mutation == "profile":
                await db.execute(
                    update(ProfileRow)
                    .where(ProfileRow.user_id == ids["owner"])
                    .values(source_kind="REAL")
                )
            elif mutation == "membership":
                await db.execute(
                    update(AcademicMembershipRow)
                    .where(AcademicMembershipRow.user_id == ids["owner"])
                    .values(status="inactive")
                )
            elif mutation == "role":
                await db.execute(
                    update(RoleAssignmentRow)
                    .where(RoleAssignmentRow.user_id == ids["owner"])
                    .values(status="revoked")
                )
            elif mutation == "scope":
                await db.execute(
                    update(RoleAssignmentRow)
                    .where(RoleAssignmentRow.user_id == ids["owner"])
                    .values(scope_id=uuid4())
                )
            elif mutation == "source":
                await db.execute(
                    update(AcademicMembershipRow)
                    .where(AcademicMembershipRow.user_id == ids["owner"])
                    .values(source_kind="REAL")
                )
            else:
                await db.execute(
                    update(IdentityRow)
                    .where(IdentityRow.id == ids["owner"])
                    .values(status="disabled")
                )

        execute(revoke)
        assert client.get("/api/v1/anonymous-posts", headers=headers).status_code in {401, 403}


@pytest.mark.parametrize("mutation", ["token", "approval", "role"])
def test_revocation_between_dependency_and_resource_uow_is_rechecked(platform, mutation):
    app, ids, _, execute = platform
    with TestClient(app) as client:
        token = login(client)["Authorization"].removeprefix("Bearer ")
        runtime = app.state.platform_runtime
        principal = asyncio.run(runtime.context(token)).principal

        async def revoke(db):
            if mutation == "token":
                await db.execute(
                    delete(AuthSessionRow).where(AuthSessionRow.token_hash == _token_hash(token))
                )
            elif mutation == "approval":
                await db.execute(
                    update(AuditLogRow)
                    .where(AuditLogRow.id == ids["approval_a"])
                    .values(event="revoked")
                )
            else:
                await db.execute(
                    update(RoleAssignmentRow)
                    .where(RoleAssignmentRow.user_id == ids["owner"])
                    .values(status="revoked")
                )

        execute(revoke)
        called = []
        with pytest.raises(ApiError):
            asyncio.run(runtime.run(token, principal, lambda _: called.append(True)))
        assert not called


def test_runtime_scoped_token_cleanup_does_not_delete_other_legacy_session(platform):
    app, _, _, execute = platform

    async def expired(db):
        db.add(
            AuthSessionRow(
                token_hash="a" * 64,
                student_id="DITDEMO_A",
                expires_at=datetime.now(UTC).replace(tzinfo=None) - timedelta(days=1),
            )
        )
        db.add(
            AuthSessionRow(
                token_hash="b" * 64,
                student_id="DITDEMO_B",
                expires_at=datetime.now(UTC).replace(tzinfo=None) - timedelta(days=1),
            )
        )

    execute(expired)
    with TestClient(app) as client:
        login(client)

    async def check(db):
        assert await db.get(AuthSessionRow, "a" * 64) is None
        assert await db.get(AuthSessionRow, "b" * 64) is not None

    execute(check)


def test_default_legacy_token_helper_cleanup_contract_is_preserved(platform):
    _, _, _, execute = platform

    async def check(db):
        db.add(
            AuthSessionRow(
                token_hash="c" * 64,
                student_id="DITDEMO_B",
                expires_at=datetime.now(UTC).replace(tzinfo=None) - timedelta(days=1),
            )
        )
        await db.flush()
        await issue_token(db, "DITDEMO_A")
        assert await db.get(AuthSessionRow, "c" * 64) is None

    # The existing helper commits by design, so run outside execute()'s managed transaction.
    async def run():
        async with async_sessionmaker(platform[2], expire_on_commit=False)() as db:
            await check(db)

    asyncio.run(run())


@pytest.mark.parametrize("change", ["unpin", "issuer_case", "approval_case", "approval_source"])
def test_binding_requires_exact_issuer_event_source_and_operator_pinned_id(platform, change):
    app, ids, _, execute = platform
    with TestClient(app) as client:
        headers = login(client)
        if change == "unpin":
            app.state.platform_runtime.approved_ids = frozenset({ids["approval_b"]})
        else:

            async def mutate(db):
                if change == "issuer_case":
                    await db.execute(
                        update(IdentityRow)
                        .where(IdentityRow.id == ids["owner"])
                        .values(issuer=LOGIN_ISSUER.upper())
                    )
                elif change == "approval_case":
                    await db.execute(
                        update(AuditLogRow)
                        .where(AuditLogRow.id == ids["approval_a"])
                        .values(event="IDENTITY_BINDING_APPROVED")
                    )
                else:
                    await db.execute(
                        update(AuditLogRow)
                        .where(AuditLogRow.id == ids["approval_a"])
                        .values(source_kind="REAL")
                    )

            execute(mutate)
        assert client.get("/api/v1/auth/me", headers=headers).status_code == 403


def test_approved_canonical_membership_change_uses_current_ledger_not_legacy_copy(platform):
    app, ids, _, execute = platform
    with TestClient(app) as client:
        headers = login(client)
        new_dept = uuid4()

        async def change(db):
            db.add(DepartmentRow(id=new_dept, code="DEMO_NEW", name="새 가상 학과"))
            await db.flush()
            await db.execute(
                update(AcademicMembershipRow)
                .where(AcademicMembershipRow.user_id == ids["owner"])
                .values(department_id=new_dept, academic_year=3)
            )
            await db.execute(
                update(RoleAssignmentRow)
                .where(RoleAssignmentRow.user_id == ids["owner"])
                .values(scope_id=new_dept)
            )

        execute(change)
        me = client.get("/api/v1/auth/me", headers=headers)
        assert me.status_code == 200
        assert (me.json()["data"]["department_code"], me.json()["data"]["academic_year"]) == (
            "DEMO_NEW",
            3,
        )
        assert client.get("/api/v1/anonymous-posts", headers=headers).status_code == 200


def test_business_failure_rolls_back_both_post_projection_and_claim(platform):
    from app.features.community.schemas import AnonymousPostCreate

    app, _, _, execute = platform
    with TestClient(app) as client:
        token = login(client)["Authorization"].removeprefix("Bearer ")
        runtime = app.state.platform_runtime
        principal = asyncio.run(runtime.context(token)).principal

        def failing(services):
            services.posts.create(
                services.actor,
                AnonymousPostCreate(title="가상 rollback", body="합성"),
                "rollback-intent",
            )
            raise RuntimeError("SYNTHETIC_PRIVATE_ERROR")

        with pytest.raises(RuntimeError):
            asyncio.run(runtime.run(token, principal, failing))

    async def check(db):
        for model in (AnonymousPostRow, AnonymousPostPublicRow, CommunityClaimRow):
            assert await db.scalar(select(func.count()).select_from(model)) == 0

    execute(check)


def test_token_locked_reresolve_rejects_logout_race(platform, monkeypatch):
    from unittest.mock import AsyncMock

    app, _, _, _ = platform
    with TestClient(app) as client:
        headers = login(client)
        monkeypatch.setattr(
            "app.integrations.platform_runtime.runtime.resolve_token",
            AsyncMock(side_effect=["DITDEMO_A", None]),
        )
        assert client.get("/api/v1/auth/me", headers=headers).status_code == 401


def test_schema_attestation_alone_does_not_bypass_runtime_readiness(platform, monkeypatch):
    from unittest.mock import AsyncMock

    app, ids, engine, _ = platform
    runtime = PlatformRuntime(engine, frozenset({ids["approval_a"]}))
    monkeypatch.setattr(
        "app.integrations.platform_runtime.runtime.read_only_report",
        AsyncMock(
            return_value={
                "expected_mariadb_11_4": False,
                "expected_connection_collation": True,
                "expected_schema": True,
                "column_names_ready": True,
            }
        ),
    )
    with pytest.raises(ApiError):
        asyncio.run(runtime.ensure_ready())
    assert runtime._ready is False


@pytest.mark.parametrize("root_path", ["", "/backend"])
def test_private_cache_for_success_validation_unknown_and_cors(platform, root_path):
    app, _, _, _ = platform
    with TestClient(app, root_path=root_path) as client:
        login_response = client.post(
            root_path + "/api/v1/auth/login", json={"student_id": "DITDEMO_A", "password": PASSWORD}
        )
        headers = {"Authorization": "Bearer " + login_response.json()["data"]["token"]}
        for path in (
            "/auth/me",
            "/anonymous-posts",
            "/anonymous-posts/invalid-id/extra",
            "/me/saved-opportunities",
            "/recruitments/",
            "/opportunities",
        ):
            response = client.get(
                root_path + "/api/v1" + path, headers=headers, follow_redirects=False
            )
            assert response.headers["cache-control"] == "private, no-store"
        invalid = client.post(
            root_path + "/api/v1/anonymous-posts",
            headers={**headers, "Idempotency-Key": "valid-key"},
            json={"title": "xx", "body": "x", "user_id": "INJECTED_MARKER"},
        )
        assert invalid.status_code == 400 and "INJECTED_MARKER" not in invalid.text
        assert invalid.headers["cache-control"] == "private, no-store"
        preflight = client.options(
            root_path + "/api/v1/anonymous-posts",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "DELETE",
                "Access-Control-Request-Headers": "Authorization,If-Match,Idempotency-Key",
            },
        )
        assert preflight.status_code == 200
        assert "DELETE" in preflight.headers["access-control-allow-methods"]
        assert "*" not in preflight.headers["access-control-allow-origin"]
