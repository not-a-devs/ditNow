"""Collaboration application service. All authorization is decided here, server-side.

Order inside every transaction: participation grant (403) -> parent scope/visibility (404) ->
ownership/group grant (404, never confirming another user's resource) -> idempotency claim ->
state/revision checks (409) -> write. Because the grant is re-read on every request, a replay
after revocation is refused before the stored record is consulted.
"""

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import replace
from datetime import datetime
from uuid import uuid4

from app.core.errors import ApiError
from app.features.collaboration.domain import (
    PAGE_MAX,
    BookmarkRecord,
    CollaborationActor,
    CommentRecord,
    CommentStatus,
    GroupGrant,
    GroupKind,
    GroupOrigin,
    GroupRecord,
    GroupRole,
    GroupStatus,
    JoinMode,
    MembershipRecord,
    MembershipStatus,
    ReportRecord,
    ReportStatus,
    ReportTargetType,
    SourceKind,
    SourceRef,
    SpacePostRecord,
    SpacePostStatus,
    excerpt,
    has_open_seat,
    normalize_source,
    require_aware_utc,
)
from app.features.collaboration.idempotency import new_record, replayed_resource
from app.features.collaboration.ports import CollaborationStore, CollaborationUnitOfWork
from app.features.collaboration.schemas import (
    BookmarkPublic,
    BookmarkState,
    CommentCreate,
    CommentPublic,
    CommentUpdate,
    GroupCreate,
    GroupPublic,
    JoinDecision,
    JoinRequestPublic,
    MembershipLeave,
    MyMembership,
    Page,
    PostSummary,
    ProfileName,
    ReportCreate,
    ReportPublic,
    SourcePublic,
    SpacePostCreate,
    SpacePostPublic,
)
from app.features.community.domain import AnonymousPostPublicRow
from app.schemas.common import ErrorCode, utc_now

Clock = Callable[[], datetime]
IdFactory = Callable[[], str]

# Only virtual groups can be joined here; official club membership follows school rules that
# are not approved for this platform (BLOCKED_POLICY), so such catalog entries are info-only.
JOINABLE_SOURCES = frozenset({SourceKind.DEMO, SourceKind.USER_DEMO})


def new_id() -> str:
    return str(uuid4())


def _page(limit: int, offset: int) -> tuple[int, int]:
    if not 1 <= limit <= PAGE_MAX or offset < 0:
        raise ApiError(ErrorCode.VALIDATION)
    return limit, offset


def _summary(row: AnonymousPostPublicRow) -> PostSummary:
    # Field-by-field from the public projection; it has no author value to copy.
    return PostSummary(
        id=row.id,
        title=row.title,
        excerpt=excerpt(row.body),
        comment_count=row.comment_count,
        created_at=row.created_at,
    )


def _comment(record: CommentRecord, actor: CollaborationActor) -> CommentPublic:
    return CommentPublic(
        id=record.id,
        post_id=record.post_id,
        body=record.body,
        is_mine=record.author_id == actor.user_id,
        revision=record.revision,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def _report(record: ReportRecord) -> ReportPublic:
    return ReportPublic(
        id=record.id,
        target_type=record.target_type,
        target_id=record.target_id,
        reason=record.reason,
        status=record.status,
        created_at=record.created_at,
    )


def _my_membership(record: MembershipRecord | None) -> MyMembership | None:
    if record is None:
        return None
    return MyMembership(
        id=record.id, role=record.role, status=record.status, revision=record.revision
    )


class CollaborationService:
    def __init__(
        self,
        store: CollaborationStore,
        *,
        clock: Clock = utc_now,
        id_factory: IdFactory = new_id,
    ):
        self._store = store
        self._clock = clock
        self._new_id = id_factory

    def _now(self) -> datetime:
        return require_aware_utc(self._clock())

    @contextmanager
    def _tx(self, actor: CollaborationActor) -> Iterator[CollaborationUnitOfWork]:
        if not actor.user_id:
            raise ApiError(ErrorCode.UNAUTHORIZED)
        with self._store.transaction(actor.user_id) as uow:
            if not uow.participation.active:
                raise ApiError(ErrorCode.FORBIDDEN)
            yield uow

    def _claim(
        self,
        uow: CollaborationUnitOfWork,
        actor: CollaborationActor,
        *,
        path: str,
        key: str,
        payload: dict,
        resource_type: str,
        resource_id: str,
    ) -> str | None:
        attempted = new_record(
            actor_id=actor.user_id,
            path=path,
            key=key,
            payload=payload,
            resource_type=resource_type,
            resource_id=resource_id,
        )
        return replayed_resource(uow.claim(attempted), attempted)

    @staticmethod
    def _active_post(uow: CollaborationUnitOfWork, post_id: str) -> AnonymousPostPublicRow:
        row = uow.active_posts([post_id]).get(post_id)
        if row is None:
            raise ApiError(ErrorCode.NOT_FOUND)
        return row

    # ================================================================ FR-COM-002 search

    def search_posts(
        self, actor: CollaborationActor, text: str, *, limit: int, offset: int
    ) -> Page[PostSummary]:
        limit, offset = _page(limit, offset)
        with self._tx(actor) as uow:
            rows = uow.search_posts(text, limit=limit + 1, offset=offset)
        return Page(
            items=[_summary(row) for row in rows[:limit]],
            limit=limit,
            offset=offset,
            has_more=len(rows) > limit,
        )

    # ================================================================ FR-COM-002 comments

    def list_comments(
        self, actor: CollaborationActor, post_id: str, *, limit: int, offset: int
    ) -> Page[CommentPublic]:
        limit, offset = _page(limit, offset)
        with self._tx(actor) as uow:
            self._active_post(uow, post_id)
            rows = uow.list_comments(post_id, limit=limit + 1, offset=offset)
        rows = [row for row in rows if row.status is CommentStatus.ACTIVE]
        return Page(
            items=[_comment(row, actor) for row in rows[:limit]],
            limit=limit,
            offset=offset,
            has_more=len(rows) > limit,
        )

    def create_comment(
        self, actor: CollaborationActor, post_id: str, payload: CommentCreate, key: str
    ) -> tuple[CommentPublic, bool]:
        now = self._now()
        with self._tx(actor) as uow:
            self._active_post(uow, post_id)
            record = CommentRecord(
                id=self._new_id(),
                post_id=post_id,
                author_id=actor.user_id,
                body=payload.body,
                status=CommentStatus.ACTIVE,
                revision=1,
                created_at=now,
                updated_at=now,
            )
            previous = self._claim(
                uow,
                actor,
                path=f"/anonymous-posts/{post_id}/comments",
                key=key,
                payload=payload.model_dump(mode="json"),
                resource_type="comment",
                resource_id=record.id,
            )
            if previous is not None:
                stored = uow.get_comment(previous)
                # Tombstone: a deleted comment is never recreated by a replay.
                if (
                    stored is None
                    or stored.post_id != post_id
                    or stored.author_id != actor.user_id
                    or stored.status is not CommentStatus.ACTIVE
                ):
                    raise ApiError(ErrorCode.NOT_FOUND)
                return _comment(stored, actor), True
            uow.insert_comment(record)
            return _comment(record, actor), False

    def update_comment(
        self,
        actor: CollaborationActor,
        post_id: str,
        comment_id: str,
        payload: CommentUpdate,
    ) -> CommentPublic:
        now = self._now()
        with self._tx(actor) as uow:
            current = self._own_comment(uow, actor, post_id, comment_id)
            updated = replace(
                current, body=payload.body, revision=current.revision + 1, updated_at=now
            )
            self._cas(current.revision, payload.revision, uow.cas_comment, updated)
            return _comment(updated, actor)

    def delete_comment(
        self, actor: CollaborationActor, post_id: str, comment_id: str, revision: int
    ) -> str:
        now = self._now()
        with self._tx(actor) as uow:
            current = self._own_comment(uow, actor, post_id, comment_id)
            # Soft delete keeps a body-less tombstone so idempotency replays cannot revive it.
            tombstone = replace(
                current,
                body="",
                status=CommentStatus.DELETED,
                revision=current.revision + 1,
                updated_at=now,
            )
            self._cas(current.revision, revision, uow.cas_comment, tombstone)
            return current.id

    def _own_comment(
        self,
        uow: CollaborationUnitOfWork,
        actor: CollaborationActor,
        post_id: str,
        comment_id: str,
    ) -> CommentRecord:
        self._active_post(uow, post_id)
        record = uow.get_comment(comment_id)
        if (
            record is None
            or record.post_id != post_id
            or record.status is not CommentStatus.ACTIVE
            or record.author_id != actor.user_id
        ):
            raise ApiError(ErrorCode.NOT_FOUND)
        return record

    @staticmethod
    def _cas(current_revision: int, expected: int, cas: Callable, updated) -> None:
        if current_revision != expected or not cas(updated, expected):
            raise ApiError(ErrorCode.CONFLICT)

    # ================================================================ FR-COM-002 bookmarks

    def add_bookmark(self, actor: CollaborationActor, post_id: str) -> BookmarkState:
        now = self._now()
        with self._tx(actor) as uow:
            self._active_post(uow, post_id)
            uow.add_bookmark(BookmarkRecord(user_id=actor.user_id, post_id=post_id, created_at=now))
        return BookmarkState(post_id=post_id, bookmarked=True)

    def remove_bookmark(self, actor: CollaborationActor, post_id: str) -> BookmarkState:
        # Scoped to the caller's own rows; allowed even after the post was deleted.
        with self._tx(actor) as uow:
            uow.remove_bookmark(actor.user_id, post_id)
        return BookmarkState(post_id=post_id, bookmarked=False)

    def list_bookmarks(
        self, actor: CollaborationActor, *, limit: int, offset: int
    ) -> Page[BookmarkPublic]:
        limit, offset = _page(limit, offset)
        with self._tx(actor) as uow:
            rows = uow.list_bookmarks(actor.user_id, limit=limit + 1, offset=offset)
            visible = uow.active_posts([row.post_id for row in rows[:limit]])
        items = [
            BookmarkPublic(post=_summary(visible[row.post_id]), bookmarked_at=row.created_at)
            for row in rows[:limit]
            if row.user_id == actor.user_id and row.post_id in visible
        ]
        return Page(items=items, limit=limit, offset=offset, has_more=len(rows) > limit)

    # ================================================================ FR-COM-003 reports

    def create_report(
        self, actor: CollaborationActor, payload: ReportCreate, key: str
    ) -> tuple[ReportPublic, bool]:
        now = self._now()
        with self._tx(actor) as uow:
            if self._is_own_target(uow, actor, payload.target_type, payload.target_id):
                raise ApiError(ErrorCode.CONFLICT)
            record = ReportRecord(
                id=self._new_id(),
                reporter_id=actor.user_id,
                target_type=payload.target_type,
                target_id=payload.target_id,
                reason=payload.reason,
                status=ReportStatus.SUBMITTED,
                created_at=now,
            )
            previous = self._claim(
                uow,
                actor,
                path="/reports",
                key=key,
                payload=payload.model_dump(mode="json"),
                resource_type="report",
                resource_id=record.id,
            )
            if previous is not None:
                stored = uow.get_report(previous)
                if stored is None or stored.reporter_id != actor.user_id:
                    raise ApiError(ErrorCode.NOT_FOUND)
                return _report(stored), True
            if uow.find_report(actor.user_id, payload.target_type, payload.target_id):
                # One report per reporter and target; raising also rolls back the claim.
                raise ApiError(ErrorCode.CONFLICT)
            uow.insert_report(record)
            return _report(record), False

    def _is_own_target(
        self,
        uow: CollaborationUnitOfWork,
        actor: CollaborationActor,
        target_type: ReportTargetType,
        target_id: str,
    ) -> bool:
        """Visibility first (404), then a server-internal ownership probe never returned."""
        if target_type is ReportTargetType.ANONYMOUS_POST:
            self._active_post(uow, target_id)
            return uow.post_author_is(target_id, actor.user_id)
        comment = uow.get_comment(target_id)
        if comment is None or comment.status is not CommentStatus.ACTIVE:
            raise ApiError(ErrorCode.NOT_FOUND)
        self._active_post(uow, comment.post_id)
        return comment.author_id == actor.user_id

    def list_my_reports(
        self, actor: CollaborationActor, *, limit: int, offset: int
    ) -> Page[ReportPublic]:
        limit, offset = _page(limit, offset)
        with self._tx(actor) as uow:
            rows = uow.list_reports(actor.user_id, limit=limit + 1, offset=offset)
        mine = [row for row in rows if row.reporter_id == actor.user_id]
        return Page(
            items=[_report(row) for row in mine[:limit]],
            limit=limit,
            offset=offset,
            has_more=len(rows) > limit,
        )

    # ================================================================ FR-COM-006 groups

    def list_groups(
        self,
        actor: CollaborationActor,
        *,
        kind: GroupKind | None,
        text: str | None,
        limit: int,
        offset: int,
    ) -> Page[GroupPublic]:
        limit, offset = _page(limit, offset)
        now = self._now()
        with self._tx(actor) as uow:
            rows = uow.list_groups(kind=kind, text=text, limit=limit + 1, offset=offset)
            page = [row for row in rows[:limit] if row.status is GroupStatus.OPEN]
            items = self._present_groups(uow, actor, page, now)
        return Page(items=items, limit=limit, offset=offset, has_more=len(rows) > limit)

    def get_group(self, actor: CollaborationActor, group_id: str) -> GroupPublic:
        now = self._now()
        with self._tx(actor) as uow:
            group = self._visible_group(uow, actor, group_id)
            return self._present_groups(uow, actor, [group], now)[0]

    def create_group(
        self, actor: CollaborationActor, payload: GroupCreate, key: str
    ) -> tuple[GroupPublic, bool]:
        now = self._now()
        with self._tx(actor) as uow:
            group = GroupRecord(
                id=self._new_id(),
                kind=payload.kind,
                name=payload.name,
                description=payload.description,
                join_mode=payload.join_mode,
                capacity=payload.capacity,
                member_count=1,
                status=GroupStatus.OPEN,
                origin=GroupOrigin.MEMBER_CREATED,
                # Student-made groups are user demo content, never an official club record.
                source=SourceRef(SourceKind.USER_DEMO),
                revision=1,
                created_at=now,
                updated_at=now,
            )
            previous = self._claim(
                uow,
                actor,
                path="/groups",
                key=key,
                payload=payload.model_dump(mode="json"),
                resource_type="group",
                resource_id=group.id,
            )
            if previous is not None:
                stored = self._visible_group(uow, actor, previous)
                return self._present_groups(uow, actor, [stored], now)[0], True
            uow.insert_group(group)
            uow.insert_membership(
                MembershipRecord(
                    id=self._new_id(),
                    group_id=group.id,
                    user_id=actor.user_id,
                    role=GroupRole.LEADER,
                    status=MembershipStatus.ACTIVE,
                    revision=1,
                    created_at=now,
                    updated_at=now,
                )
            )
            return self._present_groups(uow, actor, [group], now)[0], False

    def request_join(
        self, actor: CollaborationActor, group_id: str, key: str
    ) -> tuple[MyMembership, bool]:
        now = self._now()
        with self._tx(actor) as uow:
            group = self._visible_group(uow, actor, group_id, for_update=True)
            existing = uow.memberships_of(actor.user_id, [group_id]).get(group_id)
            # Re-joining after leaving reuses the UNIQUE(group_id, user_id) row, so the claim
            # must point at that row for later replays.
            membership_id = existing.id if existing is not None else self._new_id()
            previous = self._claim(
                uow,
                actor,
                path=f"/groups/{group_id}/join-requests",
                key=key,
                payload={},
                resource_type="membership",
                resource_id=membership_id,
            )
            if previous is not None:
                stored = uow.get_membership(previous)
                if stored is None or stored.group_id != group_id or stored.user_id != actor.user_id:
                    raise ApiError(ErrorCode.NOT_FOUND)
                return MyMembership(
                    id=stored.id, role=stored.role, status=stored.status, revision=stored.revision
                ), True
            if group.status is not GroupStatus.OPEN or group.source.kind not in JOINABLE_SOURCES:
                raise ApiError(ErrorCode.CONFLICT)
            if existing is not None and existing.status is not MembershipStatus.LEFT:
                # pending/active duplicates and re-requests after rejection are refused.
                raise ApiError(ErrorCode.CONFLICT)
            target = (
                MembershipStatus.ACTIVE
                if group.join_mode is JoinMode.OPEN
                else MembershipStatus.PENDING
            )
            if target is MembershipStatus.ACTIVE:
                self._take_seat(uow, group, now)
            if existing is None:
                record = MembershipRecord(
                    id=membership_id,
                    group_id=group_id,
                    user_id=actor.user_id,
                    role=GroupRole.MEMBER,
                    status=target,
                    revision=1,
                    created_at=now,
                    updated_at=now,
                )
                uow.insert_membership(record)
            else:
                record = replace(
                    existing,
                    role=GroupRole.MEMBER,
                    status=target,
                    revision=existing.revision + 1,
                    updated_at=now,
                )
                if not uow.cas_membership(record, existing.revision):
                    raise ApiError(ErrorCode.CONFLICT)
            return MyMembership(
                id=record.id, role=record.role, status=record.status, revision=record.revision
            ), False

    def list_join_requests(
        self, actor: CollaborationActor, group_id: str, *, limit: int, offset: int
    ) -> Page[JoinRequestPublic]:
        limit, offset = _page(limit, offset)
        with self._tx(actor) as uow:
            self._leader_scope(uow, actor, group_id)
            rows = uow.list_memberships(
                group_id, MembershipStatus.PENDING, limit=limit + 1, offset=offset
            )
            page = [row for row in rows[:limit] if row.group_id == group_id]
            names = uow.display_names({row.user_id for row in page})
        items = [
            JoinRequestPublic(
                id=row.id,
                group_id=row.group_id,
                applicant=ProfileName(display_name=names.get(row.user_id)),
                status=row.status,
                revision=row.revision,
                created_at=row.created_at,
            )
            for row in page
        ]
        return Page(items=items, limit=limit, offset=offset, has_more=len(rows) > limit)

    def decide_join(
        self,
        actor: CollaborationActor,
        group_id: str,
        membership_id: str,
        payload: JoinDecision,
    ) -> JoinRequestPublic:
        now = self._now()
        with self._tx(actor) as uow:
            group = self._leader_scope(uow, actor, group_id, for_update=True)
            current = uow.get_membership(membership_id)
            if current is None or current.group_id != group_id:
                raise ApiError(ErrorCode.NOT_FOUND)
            if current.status is not MembershipStatus.PENDING:
                raise ApiError(ErrorCode.CONFLICT)
            target = (
                MembershipStatus.ACTIVE
                if payload.decision == "approve"
                else MembershipStatus.REJECTED
            )
            if target is MembershipStatus.ACTIVE:
                if group.status is not GroupStatus.OPEN:
                    raise ApiError(ErrorCode.CONFLICT)
                self._take_seat(uow, group, now)
            updated = replace(current, status=target, revision=current.revision + 1, updated_at=now)
            self._cas(current.revision, payload.revision, uow.cas_membership, updated)
            names = uow.display_names({updated.user_id})
        return JoinRequestPublic(
            id=updated.id,
            group_id=group_id,
            applicant=ProfileName(display_name=names.get(updated.user_id)),
            status=updated.status,
            revision=updated.revision,
            created_at=updated.created_at,
        )

    def leave_group(
        self, actor: CollaborationActor, group_id: str, payload: MembershipLeave
    ) -> MyMembership:
        now = self._now()
        with self._tx(actor) as uow:
            group = uow.get_group(group_id, for_update=True)
            grant = uow.group_grant(group_id, actor.user_id) if group else None
            current = uow.memberships_of(actor.user_id, [group_id]).get(group_id)
            if (
                group is None
                or current is None
                or current.status not in (MembershipStatus.ACTIVE, MembershipStatus.PENDING)
            ):
                raise ApiError(ErrorCode.NOT_FOUND)
            if current.role is GroupRole.LEADER or (grant is not None and grant.is_leader):
                # Leader hand-over is an undecided policy; the leader cannot leave.
                raise ApiError(ErrorCode.CONFLICT)
            was_active = current.status is MembershipStatus.ACTIVE
            updated = replace(
                current,
                status=MembershipStatus.LEFT,
                revision=current.revision + 1,
                updated_at=now,
            )
            self._cas(current.revision, payload.revision, uow.cas_membership, updated)
            if was_active:
                freed = replace(
                    group,
                    member_count=max(1, group.member_count - 1),
                    revision=group.revision + 1,
                    updated_at=now,
                )
                if not uow.cas_group(freed, group.revision):
                    raise ApiError(ErrorCode.CONFLICT)
            return MyMembership(
                id=updated.id, role=updated.role, status=updated.status, revision=updated.revision
            )

    def _take_seat(self, uow: CollaborationUnitOfWork, group: GroupRecord, now: datetime) -> None:
        # Runs under the group row lock taken by ``get_group(for_update=True)``.
        if not has_open_seat(group):
            raise ApiError(ErrorCode.CONFLICT)
        taken = replace(
            group,
            member_count=group.member_count + 1,
            revision=group.revision + 1,
            updated_at=now,
        )
        if not uow.cas_group(taken, group.revision):
            raise ApiError(ErrorCode.CONFLICT)

    def _visible_group(
        self,
        uow: CollaborationUnitOfWork,
        actor: CollaborationActor,
        group_id: str,
        *,
        for_update: bool = False,
    ) -> GroupRecord:
        group = uow.get_group(group_id, for_update=for_update)
        if group is None:
            raise ApiError(ErrorCode.NOT_FOUND)
        if (
            group.status is not GroupStatus.OPEN
            and not uow.group_grant(group_id, actor.user_id).is_member
        ):
            raise ApiError(ErrorCode.NOT_FOUND)
        return group

    def _leader_scope(
        self,
        uow: CollaborationUnitOfWork,
        actor: CollaborationActor,
        group_id: str,
        *,
        for_update: bool = False,
    ) -> GroupRecord:
        group = uow.get_group(group_id, for_update=for_update)
        if group is None or not uow.group_grant(group_id, actor.user_id).is_leader:
            raise ApiError(ErrorCode.NOT_FOUND)
        return group

    def _member_scope(
        self, uow: CollaborationUnitOfWork, actor: CollaborationActor, group_id: str
    ) -> GroupGrant:
        group = uow.get_group(group_id)
        grant = uow.group_grant(group_id, actor.user_id) if group else None
        if grant is None or not grant.is_member:
            raise ApiError(ErrorCode.NOT_FOUND)
        return grant

    def _present_groups(
        self,
        uow: CollaborationUnitOfWork,
        actor: CollaborationActor,
        groups: list[GroupRecord],
        now: datetime,
    ) -> list[GroupPublic]:
        ids = [group.id for group in groups]
        leaders = uow.leader_ids(ids)
        names = uow.display_names(set(leaders.values()))
        mine = uow.memberships_of(actor.user_id, ids)
        result = []
        for group in groups:
            source = normalize_source(group.source, now)
            result.append(
                GroupPublic(
                    id=group.id,
                    kind=group.kind,
                    name=group.name,
                    description=group.description,
                    join_mode=group.join_mode,
                    capacity=group.capacity,
                    member_count=group.member_count,
                    status=group.status,
                    origin=group.origin,
                    source=SourcePublic(
                        kind=source.kind, url=source.url, checked_at=source.checked_at
                    ),
                    leader=ProfileName(display_name=names.get(leaders.get(group.id, ""))),
                    my_membership=_my_membership(mine.get(group.id)),
                    revision=group.revision,
                    created_at=group.created_at,
                    updated_at=group.updated_at,
                )
            )
        return result

    # ================================================================ FR-COM-007 team space

    def list_space_posts(
        self, actor: CollaborationActor, group_id: str, *, limit: int, offset: int
    ) -> Page[SpacePostPublic]:
        limit, offset = _page(limit, offset)
        with self._tx(actor) as uow:
            self._member_scope(uow, actor, group_id)
            rows = list(uow.list_space_posts(group_id, limit=limit + 1, offset=offset))
            page = [
                row
                for row in rows[:limit]
                if row.group_id == group_id and row.status is SpacePostStatus.ACTIVE
            ]
            names = uow.display_names({row.author_id for row in page})
        return Page(
            items=[self._space_post(row, actor, names) for row in page],
            limit=limit,
            offset=offset,
            has_more=len(rows) > limit,
        )

    def create_space_post(
        self, actor: CollaborationActor, group_id: str, payload: SpacePostCreate, key: str
    ) -> tuple[SpacePostPublic, bool]:
        now = self._now()
        with self._tx(actor) as uow:
            self._member_scope(uow, actor, group_id)
            record = SpacePostRecord(
                id=self._new_id(),
                group_id=group_id,
                author_id=actor.user_id,
                body=payload.body,
                status=SpacePostStatus.ACTIVE,
                revision=1,
                created_at=now,
                updated_at=now,
            )
            previous = self._claim(
                uow,
                actor,
                path=f"/groups/{group_id}/space/posts",
                key=key,
                payload=payload.model_dump(mode="json"),
                resource_type="space_post",
                resource_id=record.id,
            )
            if previous is not None:
                stored = uow.get_space_post(previous)
                if (
                    stored is None
                    or stored.group_id != group_id
                    or stored.author_id != actor.user_id
                    or stored.status is not SpacePostStatus.ACTIVE
                ):
                    raise ApiError(ErrorCode.NOT_FOUND)
                record, replayed = stored, True
            else:
                uow.insert_space_post(record)
                replayed = False
            names = uow.display_names({actor.user_id})
            return self._space_post(record, actor, names), replayed

    def delete_space_post(
        self, actor: CollaborationActor, group_id: str, post_id: str, revision: int
    ) -> str:
        now = self._now()
        with self._tx(actor) as uow:
            self._member_scope(uow, actor, group_id)
            current = uow.get_space_post(post_id)
            if (
                current is None
                or current.group_id != group_id
                or current.status is not SpacePostStatus.ACTIVE
                or current.author_id != actor.user_id
            ):
                raise ApiError(ErrorCode.NOT_FOUND)
            tombstone = replace(
                current,
                body="",
                status=SpacePostStatus.DELETED,
                revision=current.revision + 1,
                updated_at=now,
            )
            self._cas(current.revision, revision, uow.cas_space_post, tombstone)
            return current.id

    @staticmethod
    def _space_post(
        row: SpacePostRecord, actor: CollaborationActor, names: dict[str, str]
    ) -> SpacePostPublic:
        return SpacePostPublic(
            id=row.id,
            group_id=row.group_id,
            author=ProfileName(display_name=names.get(row.author_id)),
            is_mine=row.author_id == actor.user_id,
            body=row.body,
            revision=row.revision,
            created_at=row.created_at,
        )
