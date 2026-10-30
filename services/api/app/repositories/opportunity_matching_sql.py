"""Read current canonical academic context inside the verified P0 transaction.

No identity provisioning, copied academic ledger, token claims or caller scope are used.
"""

from collections.abc import Callable
from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import AcademicMembershipRow, DepartmentRow
from app.features.opportunity_matching.ports import AcademicContext, AcademicMembership
from app.repositories.p0_access import CurrentP0Access


class SQLAcademicContext:
    def __init__(self, session: Session, access: CurrentP0Access, clock: Callable[[], datetime]):
        self.session, self.access, self.clock = session, access, clock

    def current(self, user_id: UUID) -> AcademicContext | None:
        if user_id != self.access.actor_id:
            return None
        self.access.require(student=True)
        now = self.clock()
        memberships = list(
            self.session.scalars(
                select(AcademicMembershipRow)
                .where(
                    AcademicMembershipRow.user_id == user_id,
                    AcademicMembershipRow.status == "active",
                    AcademicMembershipRow.valid_from <= now,
                    (AcademicMembershipRow.valid_to.is_(None))
                    | (AcademicMembershipRow.valid_to > now),
                )
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        )
        if len(memberships) != 1 or memberships[0].source_kind != "DEMO":
            return None
        membership = memberships[0]
        department = self.session.scalar(
            select(DepartmentRow)
            .where(DepartmentRow.id == membership.department_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if department is None or department.source_kind != "DEMO":
            return None
        return AcademicContext(
            user_id,
            (AcademicMembership(department.code, membership.academic_year),),
        )
