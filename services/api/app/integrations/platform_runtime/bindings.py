"""Read only operator-approved DEMO bindings. Never creates identities, roles or approvals."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from chatbot.app.models import StudentRow
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import VerifiedPrincipal
from app.core.errors import ApiError
from app.db.models import (
    AcademicMembershipRow,
    AuditLogRow,
    DepartmentRow,
    IdentityRow,
    ProfileRow,
    RoleAssignmentRow,
    subject_digest,
)
from app.integrations.platform_runtime.models import SessionProfile
from app.repositories.p0_access import CurrentP0Access
from app.schemas.common import ErrorCode

LOGIN_ISSUER = "urn:ditnow:student-login:demo:v1"
APPROVAL_EVENT = "identity_binding_approved"
APPROVAL_RESOURCE = "identity_binding"


@dataclass(frozen=True)
class BoundSession:
    student_id: str
    principal: VerifiedPrincipal
    profile: SessionProfile


def bind_student(
    session: Session, student: StudentRow, approved_ids: frozenset[UUID], now: datetime
) -> BoundSession:
    if not approved_ids:
        raise ApiError(ErrorCode.UNAVAILABLE)
    identity = session.scalar(
        select(IdentityRow)
        .where(IdentityRow.binding_digest == subject_digest(LOGIN_ISSUER, student.student_id))
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if identity is None or (
        identity.issuer,
        identity.subject,
        identity.status,
        identity.source_kind,
    ) != (LOGIN_ISSUER, student.student_id, "active", "DEMO"):
        raise ApiError(ErrorCode.FORBIDDEN)
    approvals = list(
        session.scalars(
            select(AuditLogRow)
            .where(AuditLogRow.id.in_(approved_ids), AuditLogRow.entity_id == identity.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    )
    approvals = [
        a
        for a in approvals
        if (a.event, a.resource_kind, a.source_kind) == (APPROVAL_EVENT, APPROVAL_RESOURCE, "DEMO")
    ]
    if len(approvals) != 1 or approvals[0].actor_id in {None, identity.id}:
        raise ApiError(ErrorCode.FORBIDDEN)
    operator = session.scalar(
        select(IdentityRow)
        .where(IdentityRow.id == approvals[0].actor_id)
        .with_for_update(read=True)
        .execution_options(populate_existing=True)
    )
    operator_role = session.scalar(
        select(RoleAssignmentRow.id)
        .where(RoleAssignmentRow.user_id == approvals[0].actor_id)
        .limit(1)
        .with_for_update(read=True)
    )
    if (
        operator is None
        or (operator.status, operator.source_kind) != ("disabled", "DEMO")
        or operator_role
    ):
        raise ApiError(ErrorCode.FORBIDDEN)
    # Lock current records, then reuse the common role/scope evaluator. A grade never grants a role.
    profile = session.scalar(
        select(ProfileRow).where(ProfileRow.user_id == identity.id).with_for_update()
    )
    CurrentP0Access(session, identity.id, lambda: now).require(student=True)
    memberships = list(
        session.scalars(
            select(AcademicMembershipRow)
            .where(
                AcademicMembershipRow.user_id == identity.id,
                AcademicMembershipRow.status == "active",
                AcademicMembershipRow.valid_from <= now,
                (AcademicMembershipRow.valid_to.is_(None)) | (AcademicMembershipRow.valid_to > now),
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    )
    if len(memberships) != 1 or memberships[0].source_kind != "DEMO" or profile is None:
        raise ApiError(ErrorCode.FORBIDDEN)
    membership = memberships[0]
    department = session.scalar(
        select(DepartmentRow)
        .where(DepartmentRow.id == membership.department_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    roles = list(
        session.scalars(
            select(RoleAssignmentRow)
            .where(
                RoleAssignmentRow.user_id == identity.id,
                RoleAssignmentRow.role == "student",
                RoleAssignmentRow.status == "active",
                RoleAssignmentRow.valid_from <= now,
                (RoleAssignmentRow.valid_to.is_(None)) | (RoleAssignmentRow.valid_to > now),
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    )
    approved_role = any(
        r.source_kind == "DEMO"
        and (
            (r.scope_type == "platform" and r.scope_id is None)
            or (r.scope_type == "department" and r.scope_id == membership.department_id)
        )
        for r in roles
    )
    if not approved_role or department is None or department.source_kind != "DEMO":
        raise ApiError(ErrorCode.FORBIDDEN)
    return BoundSession(
        student.student_id,
        VerifiedPrincipal(user_id=identity.id, active=True),
        SessionProfile(
            user_id=identity.id,
            display_name=profile.display_name,
            department_id=department.id,
            department_code=department.code,
            academic_year=membership.academic_year,
            community_access=True,
        ),
    )
