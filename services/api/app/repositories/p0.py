"""Scoped P0 persistence helpers. Not mounted and not a replacement for FastAPI authorization.

The caller supplies an identity derived from a trusted session and rechecks current role/scope.
No helper creates users, grants roles, or opens an external connection.

Legacy PR #19 compatibility proposal only. New runtime must use p0_runtime.P0Executor
and community_sql/opportunities_sql; AnonymousPostRepository below reads the private
table for projection and is not approved as the student public-read adapter. Keep it
unmounted until separately replaced/retired; its tests do not establish runtime access.
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.db.models import (
    AcademicMembershipRow,
    AnonymousPostRow,
    IdentityRow,
    OpportunityCheckItemRow,
    ProfileRow,
    SavedOpportunityRow,
    subject_digest,
)
from app.schemas.common import ErrorCode, utc_now
from app.schemas.p0 import AnonymousPostPublic, VerifiedSubject


class IdentityRepository:
    def __init__(self, session: Session):
        self.session = session

    def resolve_verified_subject(self, subject: VerifiedSubject) -> UUID | None:
        """Call only after issuer/subject verification; never match by email or auto-provision."""
        identity = self.session.scalar(
            select(IdentityRow)
            .join(ProfileRow, ProfileRow.user_id == IdentityRow.id)
            .where(
                IdentityRow.binding_digest == subject_digest(subject.issuer, subject.subject),
                IdentityRow.status == "active",
            )
        )
        if identity is None or (identity.issuer, identity.subject) != (
            subject.issuer,
            subject.subject,
        ):
            return None
        return identity.id

    def current_primary_membership(
        self, user_id: UUID, at: datetime
    ) -> AcademicMembershipRow | None:
        active = list(
            self.session.scalars(
                select(AcademicMembershipRow)
                .join(IdentityRow, IdentityRow.id == AcademicMembershipRow.user_id)
                .where(
                    AcademicMembershipRow.user_id == user_id,
                    AcademicMembershipRow.status == "active",
                    IdentityRow.status == "active",
                    AcademicMembershipRow.valid_from <= at,
                    (AcademicMembershipRow.valid_to.is_(None))
                    | (AcademicMembershipRow.valid_to > at),
                )
                .limit(2)
            )
        )
        # Overlapping primary affiliations are not silently resolved into wider access.
        return active[0] if len(active) == 1 else None


class SavedOpportunityRepository:
    def __init__(self, session: Session, actor_id: UUID):
        self.session = session
        self.actor_id = actor_id

    def get(self, saved_id: UUID) -> SavedOpportunityRow:
        row = self.session.scalar(
            select(SavedOpportunityRow).where(
                SavedOpportunityRow.id == saved_id,
                SavedOpportunityRow.user_id == self.actor_id,
            )
        )
        if row is None:
            raise ApiError(ErrorCode.NOT_FOUND)
        return row

    def get_check(self, saved_id: UUID, check_id: UUID) -> OpportunityCheckItemRow:
        row = self.session.scalar(
            select(OpportunityCheckItemRow)
            .join(
                SavedOpportunityRow,
                SavedOpportunityRow.id == OpportunityCheckItemRow.saved_opportunity_id,
            )
            .where(
                OpportunityCheckItemRow.id == check_id,
                SavedOpportunityRow.id == saved_id,
                SavedOpportunityRow.user_id == self.actor_id,
            )
        )
        if row is None:
            raise ApiError(ErrorCode.NOT_FOUND)
        return row

    def update_memo(self, saved_id: UUID, *, expected_revision: int, memo: str) -> None:
        if expected_revision < 1 or len(memo) > 5000:
            raise ApiError(ErrorCode.VALIDATION)
        result = self.session.execute(
            update(SavedOpportunityRow)
            .where(
                SavedOpportunityRow.id == saved_id,
                SavedOpportunityRow.user_id == self.actor_id,
                SavedOpportunityRow.revision == expected_revision,
            )
            .values(
                memo=memo,
                revision=SavedOpportunityRow.revision + 1,
                updated_at=utc_now(),
            )
            .execution_options(synchronize_session=False)
        )
        if result.rowcount != 1:
            self.get(saved_id)  # Missing and other-owned records are both 404.
            raise ApiError(ErrorCode.CONFLICT)
        self.session.expire_all()


class AnonymousPostRepository:
    def __init__(self, session: Session, actor_id: UUID):
        self.session = session
        self.actor_id = actor_id

    def get_public(self, post_id: UUID) -> AnonymousPostPublic:
        row = (
            self.session.execute(
                select(
                    AnonymousPostRow.id,
                    AnonymousPostRow.revision,
                    AnonymousPostRow.created_at,
                    AnonymousPostRow.updated_at,
                    AnonymousPostRow.title,
                    AnonymousPostRow.body,
                    (AnonymousPostRow.author_id == self.actor_id).label("is_mine"),
                ).where(AnonymousPostRow.id == post_id, AnonymousPostRow.status == "active")
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise ApiError(ErrorCode.NOT_FOUND)
        return AnonymousPostPublic(**row, comment_count=0, origin={"source_kind": "USER_DEMO"})
