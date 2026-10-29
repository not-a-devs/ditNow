"""Current database checks behind a separately verified principal; never issues identities."""

from collections.abc import Callable
from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.db.models import (
    AcademicMembershipRow,
    IdentityRow,
    ProfileRow,
    RoleAssignmentRow,
)
from app.schemas.common import ErrorCode, utc_now


class CurrentP0Access:
    def __init__(self, session: Session, actor_id: UUID, clock: Callable[[], datetime] = utc_now):
        self.session, self.actor_id, self.clock = session, actor_id, clock

    def require(self, *, student: bool = False) -> UUID:
        identity = self.session.scalar(
            select(IdentityRow)
            .where(IdentityRow.id == self.actor_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        profile = self.session.get(ProfileRow, self.actor_id, populate_existing=True)
        if identity is None or identity.status != "active":
            raise ApiError(ErrorCode.UNAUTHORIZED)
        # Real personal records are not authorized by this demonstration integration.
        if profile is None or profile.source_kind != "DEMO" or identity.source_kind != "DEMO":
            raise ApiError(ErrorCode.FORBIDDEN)
        if not student:
            return self.actor_id
        now = self.clock()
        if now.tzinfo is None or now.utcoffset() is None:
            raise ApiError(ErrorCode.UNAVAILABLE)
        memberships = list(
            self.session.scalars(
                select(AcademicMembershipRow)
                .where(
                    AcademicMembershipRow.user_id == self.actor_id,
                    AcademicMembershipRow.status == "active",
                    AcademicMembershipRow.valid_from <= now,
                    (AcademicMembershipRow.valid_to.is_(None))
                    | (AcademicMembershipRow.valid_to > now),
                )
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        )
        if len(memberships) != 1:
            raise ApiError(ErrorCode.FORBIDDEN)
        roles = list(
            self.session.scalars(
                select(RoleAssignmentRow)
                .where(
                    RoleAssignmentRow.user_id == self.actor_id,
                    RoleAssignmentRow.role == "student",
                    RoleAssignmentRow.status == "active",
                    RoleAssignmentRow.valid_from <= now,
                    (RoleAssignmentRow.valid_to.is_(None)) | (RoleAssignmentRow.valid_to > now),
                )
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        )
        if not any(
            (r.scope_type == "platform" and r.scope_id is None)
            or (r.scope_type == "department" and r.scope_id == memberships[0].department_id)
            for r in roles
        ):
            raise ApiError(ErrorCode.FORBIDDEN)
        return self.actor_id
