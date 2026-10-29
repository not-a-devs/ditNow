from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID, uuid4

import pytest
from fastapi import Depends, Request
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.api.dependencies import (
    VerifiedPrincipal,
    authorize,
    get_authorization_policy,
    get_identity_provider,
)
from app.core.config import Settings
from app.factory import create_app
from app.schemas.operations import IdempotencyScope, RevisionPrecondition
from app.schemas.p0 import (
    AcademicMembership,
    AnonymousPostCreate,
    AnonymousPostPrivate,
    AnonymousPostPublic,
    DemoOrigin,
    Department,
    GeneralAuditLog,
    Identity,
    Opportunity,
    OpportunityCheckItem,
    PageRequest,
    PageResponse,
    Profile,
    PublicOrigin,
    Recruitment,
    RoleAssignment,
    SavedOpportunity,
)

USER = UUID("00000000-0000-4000-8000-000000000001")
OTHER = UUID("00000000-0000-4000-8000-000000000002")
NOW = datetime(2026, 10, 30, tzinfo=UTC)
ORIGIN = {"source_kind": "DEMO"}


def record():
    return {"id": uuid4(), "revision": 1, "created_at": NOW, "updated_at": NOW}


def test_provenance_requires_url_and_checked_time_for_public_source():
    with pytest.raises(ValidationError):
        PublicOrigin(source_kind="OFFICIAL_PUBLIC")
    demo = DemoOrigin(**ORIGIN)
    assert demo.label == "시연용 가상 데이터"
    with pytest.raises(ValidationError):
        DemoOrigin(**ORIGIN, official_verified=True)


@pytest.mark.parametrize("limit", [0, 101])
def test_page_limits(limit):
    with pytest.raises(ValidationError):
        PageRequest(limit=limit)


def test_page_cursor_bound_and_no_client_scope_fields():
    with pytest.raises(ValidationError):
        PageRequest(cursor="x" * 513)
    with pytest.raises(ValidationError):
        PageRequest(user_id=OTHER)
    assert PageResponse[int](data=[1], next_cursor=None).data == [1]


def test_domain_records_can_relate_by_uuid_without_a_database():
    identity = Identity(
        **{**record(), "id": USER},
        issuer="demo",
        subject="opaque-subject",
        status="active",
        origin=ORIGIN,
    )
    profile = Profile(user_id=identity.id, display_name="가상 학생", origin=ORIGIN)
    department = Department(**record(), code="DEMO", name="가상학과", origin=ORIGIN)
    membership = AcademicMembership(
        **record(),
        user_id=profile.user_id,
        department_id=department.id,
        academic_year=2,
        status="active",
        valid_from=NOW,
        origin=ORIGIN,
    )
    role = RoleAssignment(
        **record(),
        user_id=profile.user_id,
        role="student",
        scope_type="department",
        scope_id=department.id,
        status="active",
        valid_from=NOW,
        origin=ORIGIN,
    )
    assert membership.user_id == role.user_id == identity.id
    assert membership.department_id == role.scope_id


def test_membership_period_and_scope_validation():
    with pytest.raises(ValidationError):
        AcademicMembership(
            **record(),
            user_id=USER,
            department_id=OTHER,
            academic_year=2,
            status="active",
            valid_from=NOW,
            valid_to=NOW,
            origin=ORIGIN,
        )
    with pytest.raises(ValidationError):
        RoleAssignment(
            **record(),
            user_id=USER,
            role="admin",
            scope_type="platform",
            scope_id=OTHER,
            status="active",
            valid_from=NOW,
            origin=ORIGIN,
        )


@pytest.mark.parametrize("field", ["author_id", "status", "role", "source_kind", "revision"])
def test_anonymous_create_rejects_server_owned_fields(field):
    with pytest.raises(ValidationError):
        AnonymousPostCreate(title="가상 글", body="가상 내용", **{field: "injected"})


def test_public_post_cannot_accept_private_record_or_identity_fields():
    private = AnonymousPostPrivate(
        **record(),
        author_id=USER,
        title="가상 글",
        body="가상 내용",
        status="active",
        origin=ORIGIN,
    )
    with pytest.raises(ValidationError):
        AnonymousPostPublic.model_validate(private.model_dump())
    public = AnonymousPostPublic(
        **record(), title="가상 글", body="가상 내용", comment_count=0, is_mine=False, origin=ORIGIN
    )
    assert str(USER) not in public.model_dump_json()
    assert "author_id" not in public.model_json_schema()["properties"]


def test_recruitment_and_opportunity_preparation_are_demo_records():
    opportunity = Opportunity(
        **record(),
        kind="공모전",
        title="가상 공고",
        deadline_at=NOW,
        submission_mode="external_document_submission",
        origin=ORIGIN,
    )
    recruitment = Recruitment(
        **record(),
        title="가상 모집",
        body="가상 내용",
        capacity=2,
        deadline_at=NOW,
        opportunity_id=opportunity.id,
        owner_id=USER,
        status="open",
        origin=ORIGIN,
    )
    saved = SavedOpportunity(
        **record(), user_id=USER, opportunity_id=opportunity.id, status="preparing", origin=ORIGIN
    )
    item = OpportunityCheckItem(
        **record(), saved_opportunity_id=saved.id, text="원문 확인", sort_order=0
    )
    assert recruitment.opportunity_id == saved.opportunity_id
    assert item.saved_opportunity_id == saved.id


def test_invalid_capacity_and_false_external_confirmation_are_rejected():
    with pytest.raises(ValidationError):
        Recruitment(
            **record(),
            title="가상 모집",
            body="내용",
            capacity=1,
            deadline_at=NOW,
            owner_id=USER,
            status="open",
            origin=ORIGIN,
        )
    for status in ["institution_verified", "self_reported_submitted"]:
        with pytest.raises(ValidationError):
            SavedOpportunity(
                **record(), user_id=USER, opportunity_id=OTHER, status=status, origin=ORIGIN
            )
    saved = SavedOpportunity(
        **record(),
        user_id=USER,
        opportunity_id=OTHER,
        status="self_reported_submitted",
        self_reported_submitted_at=NOW,
        origin=ORIGIN,
    )
    assert saved.self_reported_submitted_at == NOW


def test_general_audit_rejects_explicit_anonymous_identity_mapping():
    with pytest.raises(ValidationError):
        GeneralAuditLog(
            **record(),
            event="post.updated",
            resource_kind="anonymous_post",
            actor_id=USER,
            entity_id=OTHER,
        )
    audit = GeneralAuditLog(**record(), event="post.updated", resource_kind="anonymous_post")
    assert audit.actor_id is None


def test_idempotency_namespaces_users_methods_and_resource_paths():
    values = {
        "actor_id": USER,
        "method": "POST",
        "canonical_path": "/api/v1/recruitments",
        "key": "same-client-key",
        "body_digest": "a" * 64,
    }
    first = IdempotencyScope(**values)
    for change in [{"actor_id": OTHER}, {"method": "PUT"}, {"canonical_path": "/api/v1/other"}]:
        assert first.namespace != IdempotencyScope(**{**values, **change}).namespace
    # Same key with different body still needs a storage conflict check; it is not a new namespace.
    assert first.namespace == IdempotencyScope(**{**values, "body_digest": "b" * 64}).namespace
    with pytest.raises(ValidationError):
        IdempotencyScope(**{**values, "canonical_path": "/api/v1/../admin"})
    with pytest.raises(ValidationError):
        RevisionPrecondition(expected_revision=0)


def protected_app():
    app = create_app(Settings(environment="test"))

    @app.get("/test-only/{post_id}")
    def read_post(principal: Annotated[VerifiedPrincipal, Depends(authorize("read", "post_id"))]):
        return {"user_id": str(principal.user_id)}

    return app


def test_unconfigured_identity_dependency_is_closed():
    with TestClient(protected_app()) as client:
        response = client.get(
            f"/test-only/{OTHER}?user_id={USER}&role=admin",
            headers={"Authorization": "Bearer fake", "X-User-ID": str(USER)},
        )
    assert response.status_code == 503
    assert response.json()["code"] == "UNAVAILABLE"


def test_test_provider_is_not_an_authorization_policy():
    class TestProvider:
        async def verify(self, request: Request):
            return VerifiedPrincipal(user_id=USER, active=True)

    app = protected_app()
    app.dependency_overrides[get_identity_provider] = lambda: TestProvider()
    with TestClient(app) as client:
        assert client.get(f"/test-only/{OTHER}").status_code == 503


def test_policy_gets_path_resource_not_user_supplied_query():
    captured = []

    class TestProvider:
        async def verify(self, request: Request):
            return VerifiedPrincipal(user_id=USER, active=True)

    class TestPolicy:
        async def require(self, principal, action, resource_id):
            captured.append((principal.user_id, action, resource_id))

    app = protected_app()
    app.dependency_overrides[get_identity_provider] = lambda: TestProvider()
    app.dependency_overrides[get_authorization_policy] = lambda: TestPolicy()
    with TestClient(app) as client:
        assert client.get(f"/test-only/{OTHER}?resource_id={USER}").status_code == 200
    assert captured == [(USER, "read", OTHER)]


def test_inactive_test_principal_is_rejected():
    class TestProvider:
        async def verify(self, request: Request):
            return VerifiedPrincipal(user_id=USER, active=False)

    app = protected_app()
    app.dependency_overrides[get_identity_provider] = lambda: TestProvider()
    with TestClient(app) as client:
        assert client.get(f"/test-only/{OTHER}").status_code == 401


def test_proposed_models_and_dependencies_are_not_live_api_routes():
    app = create_app(Settings(environment="test"))
    schema = app.openapi()
    # Public API growth and DEC-020 legacy routes are checked by the OpenAPI snapshot.
    # This test guards the still-unapproved P0 security seam, not a public-path count.
    assert not {"Identity", "VerifiedSubject", "VerifiedPrincipal", "AnonymousPostPrivate"} & set(
        schema["components"]["schemas"]
    )
    protected = (
        "/api/v1/community",
        "/api/v1/anonymous-posts",
        "/api/v1/recruitments",
        "/api/v1/opportunities",
        "/api/v1/me/saved-opportunities",
    )
    assert not any(path.startswith(protected) for path in schema["paths"])

    def dependency_calls(dependant):
        return {dependant.call} | set().union(
            *(dependency_calls(child) for child in dependant.dependencies)
        )

    calls = set().union(
        *(dependency_calls(route.dependant) for route in app.routes if isinstance(route, APIRoute))
    )
    assert not {get_identity_provider, get_authorization_policy} & calls
