"""P0 matching HTTP/SQLite integration; no MariaDB, external network, LLM or real accounts."""

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from chatbot.app.auth import _token_hash
from chatbot.app.models import AuthSessionRow
from fastapi.testclient import TestClient
from sqlalchemy import func, select, update
from test_platform_runtime import login
from test_platform_runtime import platform as platform_fixture

from app.core.config import Settings
from app.core.errors import ApiError
from app.db.models import (
    AcademicMembershipRow,
    DepartmentRow,
    IdentityRow,
    OpportunityCheckItemRow,
    OpportunityRow,
    RecruitmentRow,
    RoleAssignmentRow,
    SavedOpportunityRow,
)
from app.factory import create_app
from app.repositories.opportunity_matching_sql import SQLAcademicContext
from app.repositories.p0_access import CurrentP0Access
from app.schemas.common import utc_now

platform = platform_fixture
PATH = "/api/v1/me/opportunity-matches"


def private(response, status=200):
    assert response.status_code == status, response.text
    assert response.headers["cache-control"] == "private, no-store"
    return response.json().get("data")


def item_ids(page):
    return {row["opportunity"]["id"] for row in page["items"]}


def scoped_catalog(ids, execute):
    extra = {name: uuid4() for name in ("department", "a", "b", "year9")}

    async def seed(db):
        db.add(DepartmentRow(id=extra["department"], code="OTHER_DEPT", name="Synthetic"))
        await db.flush()
        await db.execute(
            update(AcademicMembershipRow)
            .where(AcademicMembershipRow.user_id == ids["other"])
            .values(department_id=extra["department"], academic_year=3)
        )
        await db.execute(
            update(RoleAssignmentRow)
            .where(RoleAssignmentRow.user_id == ids["other"])
            .values(scope_id=extra["department"])
        )
        for name, scope in (
            ("a", {"level": "department", "department_codes": ["DEMO_DEPT"]}),
            ("b", {"level": "department", "department_codes": ["OTHER_DEPT"]}),
            ("year9", {"level": "grade", "academic_years": [9]}),
        ):
            db.add(
                OpportunityRow(
                    id=extra[name],
                    kind="contest",
                    title=name,
                    status="published",
                    source_kind="DEMO",
                    submission_mode="external_link",
                    target_scope=scope,
                    files=[],
                )
            )

    execute(seed)
    return extra


def test_current_two_account_scope_ignores_forged_query_and_preserves_unknowns(platform):
    app, ids, _, execute = platform
    extra = scoped_catalog(ids, execute)
    with TestClient(app) as client:
        a, b = login(client), login(client, "DITDEMO_B")
        page_a = private(
            client.get(
                PATH,
                headers=a,
                params={
                    "user_id": str(ids["other"]),
                    "department_code": "OTHER_DEPT",
                    "grade": 9,
                },
            )
        )
        page_b = private(client.get(PATH, headers=b))
        assert item_ids(page_a) == {str(ids["opportunity"]), str(extra["a"])}
        assert item_ids(page_b) == {str(ids["opportunity"]), str(extra["b"])}
        assert page_a["context"]["memberships"] == [{"department_code": "DEMO_DEPT", "grade": 2}]
        brief = private(client.get(f"{PATH}/{ids['opportunity']}/brief", headers=a))
        assert brief["opportunity"]["organization"] == ""
        assert brief["opportunity"]["original_url"] is None
        assert brief["opportunity"]["deadline_at"] is None
        assert brief["freshness"] == "UNVERIFIED"
        assert brief["recruitment"]["status"] == "NOT_CONNECTED"
        assert brief["provenance"]["ai_generated"] is False
        assert brief["provenance"]["eligibility_guaranteed"] is False
        assert all(
            not step["available"] for step in brief["procedure"] if step["code"] != "SELF_RECORD"
        )


def test_existing_token_uses_changed_canonical_scope_and_invalidates_old_cursor(platform):
    app, ids, _, execute = platform
    extra = scoped_catalog(ids, execute)
    with TestClient(app) as client:
        headers = login(client)
        first = private(client.get(PATH, headers=headers, params={"limit": 1}))
        assert first["next_cursor"]

        async def move(db):
            await db.execute(
                update(AcademicMembershipRow)
                .where(AcademicMembershipRow.user_id == ids["owner"])
                .values(department_id=extra["department"], academic_year=9)
            )
            await db.execute(
                update(RoleAssignmentRow)
                .where(RoleAssignmentRow.user_id == ids["owner"])
                .values(scope_id=extra["department"])
            )

        execute(move)
        page = private(client.get(PATH, headers=headers))
        assert item_ids(page) == {str(ids["opportunity"]), str(extra["b"]), str(extra["year9"])}
        assert page["context"]["memberships"] == [{"department_code": "OTHER_DEPT", "grade": 9}]
        private(
            client.get(PATH, headers=headers, params={"limit": 1, "cursor": first["next_cursor"]}),
            409,
        )
        # Actor binding also prevents another valid account from replaying this cursor.
        private(
            client.get(
                PATH,
                headers=login(client, "DITDEMO_B"),
                params={
                    "limit": 1,
                    "cursor": first["next_cursor"],
                },
            ),
            409,
        )


@pytest.mark.parametrize(
    "mutation",
    [
        "expired_membership",
        "pending_membership",
        "revoked_role",
        "wrong_role_scope",
        "identity_disabled",
        "identity_source",
        "membership_source",
        "department_source",
        "subject_changed",
        "expired_token",
    ],
)
def test_current_binding_denies_revoked_expired_or_incompatible_rows(platform, mutation):
    app, ids, _, execute = platform
    with TestClient(app) as client:
        headers = login(client)
        token = headers["Authorization"].removeprefix("Bearer ")

        async def change(db):
            if mutation == "expired_membership":
                statement = (
                    update(AcademicMembershipRow)
                    .where(AcademicMembershipRow.user_id == ids["owner"])
                    .values(valid_to=datetime.now(UTC) - timedelta(seconds=1))
                )
            elif mutation == "pending_membership":
                statement = (
                    update(AcademicMembershipRow)
                    .where(AcademicMembershipRow.user_id == ids["owner"])
                    .values(status="pending")
                )
            elif mutation == "revoked_role":
                statement = (
                    update(RoleAssignmentRow)
                    .where(RoleAssignmentRow.user_id == ids["owner"])
                    .values(status="revoked")
                )
            elif mutation == "wrong_role_scope":
                statement = (
                    update(RoleAssignmentRow)
                    .where(RoleAssignmentRow.user_id == ids["owner"])
                    .values(scope_id=uuid4())
                )
            elif mutation == "identity_disabled":
                statement = (
                    update(IdentityRow)
                    .where(IdentityRow.id == ids["owner"])
                    .values(status="disabled")
                )
            elif mutation == "identity_source":
                statement = (
                    update(IdentityRow)
                    .where(IdentityRow.id == ids["owner"])
                    .values(source_kind="UNKNOWN")
                )
            elif mutation == "membership_source":
                statement = (
                    update(AcademicMembershipRow)
                    .where(AcademicMembershipRow.user_id == ids["owner"])
                    .values(source_kind="UNKNOWN")
                )
            elif mutation == "department_source":
                statement = (
                    update(DepartmentRow)
                    .where(DepartmentRow.id == ids["dept"])
                    .values(source_kind="UNKNOWN")
                )
            elif mutation == "subject_changed":
                statement = (
                    update(IdentityRow)
                    .where(IdentityRow.id == ids["owner"])
                    .values(subject="changed-subject")
                )
            else:
                statement = (
                    update(AuthSessionRow)
                    .where(AuthSessionRow.token_hash == _token_hash(token))
                    .values(expires_at=datetime.now(UTC) - timedelta(seconds=1))
                )
            await db.execute(statement)

        execute(change)
        for path in (PATH, f"{PATH}/{ids['opportunity']}/brief"):
            response = client.get(path, headers=headers)
            assert response.status_code in {401, 403}
            assert response.headers["cache-control"] == "private, no-store"
            assert str(ids["opportunity"]) not in response.json()["message"]


def test_resource_uow_revalidates_token_after_dependency_and_never_calls_matcher(platform):
    app, _, _, execute = platform
    with TestClient(app) as client:
        headers = login(client)
        token = headers["Authorization"].removeprefix("Bearer ")
        runtime = app.state.platform_runtime
        principal = asyncio.run(runtime.context(token)).principal

        async def expire(db):
            await db.execute(
                update(AuthSessionRow)
                .where(AuthSessionRow.token_hash == _token_hash(token))
                .values(expires_at=datetime.now(UTC) - timedelta(seconds=1))
            )

        execute(expire)
        called = []
        with pytest.raises(ApiError):
            asyncio.run(runtime.run(token, principal, lambda s: called.append(s.matching)))
        assert called == []


def test_read_only_projection_and_context_reader_cannot_select_another_actor(platform):
    app, ids, _, execute = platform

    async def inspect(db):
        foreign = await db.run_sync(
            lambda sync: SQLAcademicContext(
                sync, CurrentP0Access(sync, ids["owner"]), utc_now
            ).current(ids["other"])
        )
        assert foreign is None
        return [
            await db.scalar(select(func.count()).select_from(model))
            for model in (
                SavedOpportunityRow,
                OpportunityCheckItemRow,
                RecruitmentRow,
            )
        ]

    before = execute(inspect)
    with TestClient(app) as client:
        headers = login(client)
        private(client.get(PATH, headers=headers))
        private(client.get(f"{PATH}/{ids['opportunity']}/brief", headers=headers))
        private(client.get(PATH), 401)
        private(client.get(PATH, headers=headers, params={"limit": 21}), 400)
        private(client.get(f"{PATH}/{uuid4()}/brief", headers=headers), 404)
    assert execute(inspect) == before == [0, 0, 0]


def test_matching_routes_only_exist_with_opt_in_and_missing_runtime_fails_closed():
    for enabled in (False, True):
        app = create_app(Settings(environment="test", p0_runtime_enabled=enabled))
        with TestClient(app) as client:
            for path in (PATH, f"{PATH}/{uuid4()}/brief"):
                private(client.get(path), 503 if enabled else 404)
