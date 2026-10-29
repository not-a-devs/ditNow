"""SQLAlchemy implementations of community Protocols; transaction commit belongs to the runner."""

import hashlib
from collections.abc import Iterable
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.db.models import (
    AnonymousPostPublicRow as PublicRow,
)
from app.db.models import (
    AnonymousPostRow,
    CommunityClaimRow,
    IdentityRow,
    ProfileRow,
    RecruitmentRow,
)
from app.features.community.domain import (
    AnonymousPostPrivate,
    AnonymousPostPublicRow,
    PostStatus,
    Recruitment,
    RecruitmentStatus,
)
from app.features.community.idempotency import IdempotencyClaim
from app.repositories.p0_access import CurrentP0Access
from app.schemas.common import ErrorCode


def namespace_digest(parts: Iterable[str]) -> bytes:
    values = [value.encode() for value in parts]
    return hashlib.sha256(b"".join(len(v).to_bytes(8, "big") + v for v in values)).digest()


def as_uuid(value: str) -> UUID:
    try:
        return UUID(value)
    except (ValueError, TypeError):
        raise ApiError(ErrorCode.NOT_FOUND) from None


def claim_from_row(row: CommunityClaimRow) -> IdempotencyClaim:
    return IdempotencyClaim(
        str(row.actor_id),
        row.method,
        row.canonical_path,
        row.key,
        row.body_digest,
        str(row.resource_id),
    )


class CommunityClaims:
    def __init__(self, session: Session, access: CurrentP0Access):
        self.session, self.access = session, access

    def create(self, claim: IdempotencyClaim, write) -> IdempotencyClaim:
        actor = self.access.require(student=True)
        if as_uuid(claim.actor_id) != actor:
            raise ApiError(ErrorCode.NOT_FOUND)
        digest = namespace_digest(claim.namespace)
        existing = self.session.scalar(
            select(CommunityClaimRow)
            .where(CommunityClaimRow.namespace_digest == digest)
            .with_for_update()
        )
        if existing is not None:
            result = claim_from_row(existing)
            if result.namespace != claim.namespace:
                raise ApiError(ErrorCode.INTERNAL)
            return result
        try:
            with self.session.begin_nested():
                self.session.add(
                    CommunityClaimRow(
                        namespace_digest=digest,
                        actor_id=actor,
                        method=claim.method,
                        canonical_path=claim.canonical_path,
                        key=claim.key,
                        body_digest=claim.body_digest,
                        resource_id=as_uuid(claim.resource_id),
                    )
                )
                self.session.flush()
                write()
                self.session.flush()
        except IntegrityError:
            existing = self.session.scalar(
                select(CommunityClaimRow)
                .where(CommunityClaimRow.namespace_digest == digest)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
            if existing is None:
                raise ApiError(ErrorCode.CONFLICT) from None
            result = claim_from_row(existing)
            if result.namespace != claim.namespace:
                raise ApiError(ErrorCode.INTERNAL) from None
            return result
        return claim


def private_post(row: AnonymousPostRow) -> AnonymousPostPrivate:
    return AnonymousPostPrivate(
        str(row.id),
        str(row.author_id),
        row.title,
        row.body,
        PostStatus(row.status),
        row.revision,
        row.created_at,
        row.updated_at,
    )


def public_post(row: PublicRow) -> AnonymousPostPublicRow:
    return AnonymousPostPublicRow(
        str(row.id),
        row.title,
        row.body,
        PostStatus(row.status),
        row.revision,
        row.comment_count,
        row.created_at,
        row.updated_at,
    )


class SQLAnonymousPosts:
    def __init__(self, session: Session, access: CurrentP0Access):
        self.session, self.access = session, access

    def create(self, post: AnonymousPostPrivate, claim: IdempotencyClaim):
        if as_uuid(post.author_id) != self.access.require(student=True):
            raise ApiError(ErrorCode.NOT_FOUND)

        def write():
            self.session.add(
                AnonymousPostRow(
                    id=as_uuid(post.id),
                    author_id=as_uuid(post.author_id),
                    title=post.title,
                    body=post.body,
                    status=post.status.value,
                    revision=post.revision,
                    created_at=post.created_at,
                    updated_at=post.updated_at,
                    source_kind="USER_DEMO",
                )
            )
            self.session.flush()
            self.session.add(
                PublicRow(
                    id=as_uuid(post.id),
                    title=post.title,
                    body=post.body,
                    status=post.status.value,
                    revision=post.revision,
                    comment_count=0,
                    created_at=post.created_at,
                    updated_at=post.updated_at,
                    source_kind="USER_DEMO",
                )
            )

        return CommunityClaims(self.session, self.access).create(claim, write)

    def get_private(self, post_id: str):
        actor = self.access.require(student=True)
        row = self.session.scalar(
            select(AnonymousPostRow)
            .where(AnonymousPostRow.id == as_uuid(post_id), AnonymousPostRow.author_id == actor)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        return private_post(row) if row else None

    def update(self, post: AnonymousPostPrivate, expected_revision: int) -> bool:
        actor = self.access.require(student=True)
        if as_uuid(post.author_id) != actor:
            return False
        result = self.session.execute(
            update(AnonymousPostRow)
            .where(
                AnonymousPostRow.id == as_uuid(post.id),
                AnonymousPostRow.author_id == actor,
                AnonymousPostRow.revision == expected_revision,
            )
            .values(
                title=post.title,
                body=post.body,
                status=post.status.value,
                revision=post.revision,
                updated_at=post.updated_at,
            )
            .execution_options(synchronize_session=False)
        )
        if result.rowcount != 1:
            return False
        # Missing projection refuses the caller-owned transaction; no private-only commit.
        projection = self.session.execute(
            update(PublicRow)
            .where(PublicRow.id == as_uuid(post.id), PublicRow.revision == expected_revision)
            .values(
                title=post.title,
                body=post.body,
                status=post.status.value,
                revision=post.revision,
                updated_at=post.updated_at,
            )
            .execution_options(synchronize_session=False)
        )
        if projection.rowcount != 1:
            raise ApiError(ErrorCode.INTERNAL)
        self.session.expire_all()
        return True

    def get_public(self, post_id: str):
        self.access.require(student=True)
        row = self.session.scalar(
            select(PublicRow)
            .where(PublicRow.id == as_uuid(post_id), PublicRow.status == "active")
            .execution_options(populate_existing=True)
        )
        return public_post(row) if row else None

    def list_public(self, *, limit: int, offset: int):
        self.access.require(student=True)
        rows = self.session.scalars(
            select(PublicRow)
            .where(PublicRow.status == "active")
            .order_by(PublicRow.created_at, PublicRow.id)
            .limit(limit)
            .offset(offset)
        )
        return [public_post(row) for row in rows]

    def owned_post_ids(self, author_id: str, post_ids: Iterable[str]):
        actor = self.access.require(student=True)
        if as_uuid(author_id) != actor:
            return set()
        return {
            str(id)
            for id in self.session.scalars(
                select(AnonymousPostRow.id).where(
                    AnonymousPostRow.author_id == actor,
                    AnonymousPostRow.id.in_([as_uuid(id) for id in post_ids]),
                )
            )
        }


def recruitment(row: RecruitmentRow) -> Recruitment:
    return Recruitment(
        str(row.id),
        str(row.owner_id),
        row.title,
        row.body,
        row.field,
        tuple(row.roles),
        row.capacity,
        row.accepted_count,
        row.deadline_at,
        RecruitmentStatus(row.status),
        str(row.opportunity_id) if row.opportunity_id else None,
        row.revision,
        row.created_at,
        row.updated_at,
    )


class SQLRecruitments:
    def __init__(self, session: Session, access: CurrentP0Access):
        self.session, self.access = session, access

    def create(self, record: Recruitment, claim: IdempotencyClaim):
        if as_uuid(record.owner_id) != self.access.require(student=True):
            raise ApiError(ErrorCode.NOT_FOUND)

        def write():
            self.session.add(
                RecruitmentRow(
                    id=as_uuid(record.id),
                    owner_id=as_uuid(record.owner_id),
                    title=record.title,
                    body=record.body,
                    field=record.field,
                    roles=list(record.roles),
                    capacity=record.capacity,
                    accepted_count=record.accepted_count,
                    deadline_at=record.deadline_at,
                    status=record.status.value,
                    opportunity_id=as_uuid(record.opportunity_id)
                    if record.opportunity_id
                    else None,
                    revision=record.revision,
                    created_at=record.created_at,
                    updated_at=record.updated_at,
                    source_kind="USER_DEMO",
                )
            )

        return CommunityClaims(self.session, self.access).create(claim, write)

    def get(self, recruitment_id: str):
        self.access.require(student=True)
        row = self.session.scalar(
            select(RecruitmentRow)
            .where(RecruitmentRow.id == as_uuid(recruitment_id))
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        return recruitment(row) if row else None

    def update(self, record: Recruitment, expected_revision: int):
        actor = self.access.require(student=True)
        current = self.session.scalar(
            select(RecruitmentRow)
            .where(RecruitmentRow.id == as_uuid(record.id), RecruitmentRow.owner_id == actor)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if (
            current is None
            or current.revision != expected_revision
            or as_uuid(record.owner_id) != actor
        ):
            return False
        if (
            record.accepted_count != current.accepted_count
            or record.capacity < current.accepted_count + 1
        ):
            return False
        result = self.session.execute(
            update(RecruitmentRow)
            .where(
                RecruitmentRow.id == current.id,
                RecruitmentRow.revision == expected_revision,
                RecruitmentRow.accepted_count + 1 <= record.capacity,
            )
            .values(
                title=record.title,
                body=record.body,
                field=record.field,
                roles=list(record.roles),
                capacity=record.capacity,
                deadline_at=record.deadline_at,
                status=record.status.value,
                revision=record.revision,
                updated_at=record.updated_at,
            )
            .execution_options(synchronize_session=False)
        )
        self.session.expire_all()
        return result.rowcount == 1

    def list(self, *, limit: int, offset: int):
        self.access.require(student=True)
        return [
            recruitment(row)
            for row in self.session.scalars(
                select(RecruitmentRow)
                .order_by(RecruitmentRow.created_at, RecruitmentRow.id)
                .limit(limit)
                .offset(offset)
            )
        ]


class SQLPublicProfiles:
    def __init__(self, session: Session, access: CurrentP0Access):
        self.session, self.access = session, access

    def display_names(self, user_ids: Iterable[str]):
        self.access.require(student=True)
        rows = self.session.execute(
            select(ProfileRow.user_id, ProfileRow.display_name)
            .join(IdentityRow, IdentityRow.id == ProfileRow.user_id)
            .where(
                ProfileRow.user_id.in_([as_uuid(id) for id in user_ids]),
                ProfileRow.source_kind == "DEMO",
                IdentityRow.status == "active",
            )
        )
        return {str(id): name for id, name in rows}
