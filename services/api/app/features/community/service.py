"""Community application services. Authorization and ownership are enforced here, server-side.

Ownership failures return NOT_FOUND (not FORBIDDEN) so another user's resource existence is not
confirmed, per the P0 contract (``타인 수정 404``).
"""

from collections.abc import Callable
from dataclasses import replace
from datetime import datetime
from uuid import uuid4

from app.core.errors import ApiError
from app.features.community.domain import (
    PAGE_MAX,
    AnonymousPostPrivate,
    AnonymousPostPublicRow,
    CommunityActor,
    PostStatus,
    Recruitment,
    RecruitmentStatus,
    effective_status,
    require_member,
    team_size,
    transition_recruitment,
)
from app.features.community.repository import (
    AnonymousPostRepository,
    PublicProfileReader,
    RecruitmentRepository,
)
from app.features.community.schemas import (
    AnonymousPostCreate,
    AnonymousPostPage,
    AnonymousPostPublic,
    AnonymousPostUpdate,
    PublicProfile,
    RecruitmentClose,
    RecruitmentCreate,
    RecruitmentPage,
    RecruitmentPublic,
    RecruitmentUpdate,
)
from app.schemas.common import ErrorCode, utc_now

Clock = Callable[[], datetime]
IdFactory = Callable[[], str]


def new_id() -> str:
    return str(uuid4())


def _page(limit: int, offset: int) -> tuple[int, int]:
    if not 1 <= limit <= PAGE_MAX or offset < 0:
        raise ApiError(ErrorCode.VALIDATION)
    return limit, offset


def _to_public_post(row: AnonymousPostPublicRow, is_mine: bool) -> AnonymousPostPublic:
    # Built field-by-field from the public row; there is no author value to copy.
    return AnonymousPostPublic(
        id=row.id,
        title=row.title,
        body=row.body,
        status=row.status,
        comment_count=row.comment_count,
        is_mine=is_mine,
        revision=row.revision,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _public_row(post: AnonymousPostPrivate, comment_count: int = 0) -> AnonymousPostPublicRow:
    return AnonymousPostPublicRow(
        id=post.id,
        title=post.title,
        body=post.body,
        status=post.status,
        revision=post.revision,
        comment_count=comment_count,
        created_at=post.created_at,
        updated_at=post.updated_at,
    )


class AnonymousPostService:
    """FR-COM-001 anonymous free board CRUD."""

    def __init__(
        self,
        posts: AnonymousPostRepository,
        *,
        clock: Clock = utc_now,
        id_factory: IdFactory = new_id,
    ):
        self._posts = posts
        self._clock = clock
        self._new_id = id_factory

    def list(
        self, actor: CommunityActor | None, *, limit: int = 20, offset: int = 0
    ) -> AnonymousPostPage:
        actor = require_member(actor)
        limit, offset = _page(limit, offset)
        rows = self._posts.list_public(limit=limit + 1, offset=offset)
        rows = [row for row in rows if row.status is PostStatus.ACTIVE]
        page, has_more = rows[:limit], len(rows) > limit
        mine = self._posts.owned_post_ids(actor.user_id, [row.id for row in page])
        return AnonymousPostPage(
            items=[_to_public_post(row, row.id in mine) for row in page],
            limit=limit,
            offset=offset,
            has_more=has_more,
        )

    def get(self, actor: CommunityActor | None, post_id: str) -> AnonymousPostPublic:
        actor = require_member(actor)
        row = self._posts.get_public(post_id)
        if row is None or row.status is not PostStatus.ACTIVE:
            raise ApiError(ErrorCode.NOT_FOUND)
        mine = self._posts.owned_post_ids(actor.user_id, [row.id])
        return _to_public_post(row, row.id in mine)

    def create(
        self, actor: CommunityActor | None, payload: AnonymousPostCreate
    ) -> AnonymousPostPublic:
        actor = require_member(actor)
        now = self._clock()
        post = AnonymousPostPrivate(
            id=self._new_id(),
            author_id=actor.user_id,
            title=payload.title,
            body=payload.body,
            status=PostStatus.ACTIVE,
            revision=1,
            created_at=now,
            updated_at=now,
        )
        self._posts.create(post)
        return _to_public_post(_public_row(post), is_mine=True)

    def update(
        self, actor: CommunityActor | None, post_id: str, payload: AnonymousPostUpdate
    ) -> AnonymousPostPublic:
        actor = require_member(actor)
        post = self._owned_active(actor, post_id)
        changes = payload.model_dump(include={"title", "body"}, exclude_unset=True)
        updated = replace(post, **changes, revision=post.revision + 1, updated_at=self._clock())
        self._save(post, updated, payload.revision)
        return _to_public_post(_public_row(updated), is_mine=True)

    def delete(self, actor: CommunityActor | None, post_id: str, revision: int) -> str:
        actor = require_member(actor)
        post = self._owned_active(actor, post_id)
        deleted = replace(
            post, status=PostStatus.DELETED, revision=post.revision + 1, updated_at=self._clock()
        )
        self._save(post, deleted, revision)
        return post.id

    def _owned_active(self, actor: CommunityActor, post_id: str) -> AnonymousPostPrivate:
        post = self._posts.get_private(post_id)
        if post is None or post.status is not PostStatus.ACTIVE or post.author_id != actor.user_id:
            raise ApiError(ErrorCode.NOT_FOUND)
        return post

    def _save(
        self, current: AnonymousPostPrivate, updated: AnonymousPostPrivate, expected: int
    ) -> None:
        if current.revision != expected or not self._posts.update(updated, expected):
            raise ApiError(ErrorCode.CONFLICT)


class RecruitmentService:
    """FR-COM-004 real-name recruitment CRUD + close. Applications (FR-COM-005) are not exposed."""

    def __init__(
        self,
        recruitments: RecruitmentRepository,
        profiles: PublicProfileReader,
        *,
        clock: Clock = utc_now,
        id_factory: IdFactory = new_id,
    ):
        self._recruitments = recruitments
        self._profiles = profiles
        self._clock = clock
        self._new_id = id_factory

    def list(
        self, actor: CommunityActor | None, *, limit: int = 20, offset: int = 0
    ) -> RecruitmentPage:
        actor = require_member(actor)
        limit, offset = _page(limit, offset)
        rows = self._recruitments.list(limit=limit + 1, offset=offset)
        page, has_more = rows[:limit], len(rows) > limit
        names = self._profiles.display_names({row.owner_id for row in page})
        now = self._clock()
        return RecruitmentPage(
            items=[self._to_public(row, actor, names, now) for row in page],
            limit=limit,
            offset=offset,
            has_more=has_more,
        )

    def get(self, actor: CommunityActor | None, recruitment_id: str) -> RecruitmentPublic:
        actor = require_member(actor)
        row = self._recruitments.get(recruitment_id)
        if row is None:
            raise ApiError(ErrorCode.NOT_FOUND)
        return self._present(row, actor)

    def create(self, actor: CommunityActor | None, payload: RecruitmentCreate) -> RecruitmentPublic:
        actor = require_member(actor)
        now = self._clock()
        if payload.deadline_at <= now:
            raise ApiError(ErrorCode.VALIDATION)
        row = Recruitment(
            id=self._new_id(),
            owner_id=actor.user_id,
            title=payload.title,
            body=payload.body,
            field=payload.field,
            roles=tuple(payload.roles),
            capacity=payload.capacity,
            accepted_count=0,
            deadline_at=payload.deadline_at,
            status=RecruitmentStatus.OPEN,
            opportunity_id=payload.opportunity_id,
            revision=1,
            created_at=now,
            updated_at=now,
        )
        self._recruitments.create(row)
        return self._present(row, actor)

    def update(
        self, actor: CommunityActor | None, recruitment_id: str, payload: RecruitmentUpdate
    ) -> RecruitmentPublic:
        actor = require_member(actor)
        current = self._owned(actor, recruitment_id)
        now = self._clock()
        if effective_status(current, now) is not RecruitmentStatus.OPEN:
            raise ApiError(ErrorCode.CONFLICT)
        changes = payload.model_dump(exclude={"revision"}, exclude_unset=True)
        if "roles" in changes:
            changes["roles"] = tuple(changes["roles"])
        if "deadline_at" in changes and payload.deadline_at <= now:
            raise ApiError(ErrorCode.VALIDATION)
        if "capacity" in changes and payload.capacity < team_size(current.accepted_count):
            raise ApiError(ErrorCode.CONFLICT)
        updated = replace(current, **changes, revision=current.revision + 1, updated_at=now)
        self._save(current, updated, payload.revision)
        return self._present(updated, actor)

    def close(
        self, actor: CommunityActor | None, recruitment_id: str, payload: RecruitmentClose
    ) -> RecruitmentPublic:
        return self._transition(actor, recruitment_id, payload.revision, RecruitmentStatus.CLOSED)

    def cancel(
        self, actor: CommunityActor | None, recruitment_id: str, payload: RecruitmentClose
    ) -> RecruitmentPublic:
        return self._transition(
            actor, recruitment_id, payload.revision, RecruitmentStatus.CANCELLED
        )

    def _transition(
        self,
        actor: CommunityActor | None,
        recruitment_id: str,
        revision: int,
        target: RecruitmentStatus,
    ) -> RecruitmentPublic:
        actor = require_member(actor)
        current = self._owned(actor, recruitment_id)
        updated = transition_recruitment(current, target, self._clock())
        self._save(current, updated, revision)
        return self._present(updated, actor)

    def _owned(self, actor: CommunityActor, recruitment_id: str) -> Recruitment:
        row = self._recruitments.get(recruitment_id)
        if row is None or row.owner_id != actor.user_id:
            raise ApiError(ErrorCode.NOT_FOUND)
        return row

    def _save(self, current: Recruitment, updated: Recruitment, expected: int) -> None:
        if current.revision != expected or not self._recruitments.update(updated, expected):
            raise ApiError(ErrorCode.CONFLICT)

    def _present(self, row: Recruitment, actor: CommunityActor) -> RecruitmentPublic:
        names = self._profiles.display_names({row.owner_id})
        return self._to_public(row, actor, names, self._clock())

    @staticmethod
    def _to_public(
        row: Recruitment, actor: CommunityActor, names: dict[str, str], now: datetime
    ) -> RecruitmentPublic:
        return RecruitmentPublic(
            id=row.id,
            owner=PublicProfile(display_name=names.get(row.owner_id)),
            is_mine=row.owner_id == actor.user_id,
            title=row.title,
            body=row.body,
            field=row.field,
            roles=list(row.roles),
            capacity=row.capacity,
            accepted_count=row.accepted_count,
            deadline_at=row.deadline_at,
            status=effective_status(row, now),
            opportunity_id=row.opportunity_id,
            revision=row.revision,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )
