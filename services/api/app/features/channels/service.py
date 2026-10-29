"""Free channel and official-request services. Every method re-checks current eligibility.

Authorization is decided here inside one unit of work, after the aggregate lock, from the
memberships the store reads in that same transaction. Routers and UI never decide access.
"""

from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from uuid import UUID, uuid4

from app.core.errors import ApiError
from app.features.academics.idempotency import claim_for, replayed_resource
from app.features.campus import policy as campus_policy
from app.features.campus.domain import CampusActor
from app.features.campus.services import check_page_size
from app.features.channels.domain import (
    MEMBER_LIMIT,
    OWNED_ACTIVE_LIMIT_PER_SCOPE,
    PAGE_MAX,
    ChannelMembership,
    ChannelsActor,
    ChannelStatus,
    FreeChannel,
    MemberRole,
    OfficialChannelRequest,
    RequestStatus,
    channel_name,
    description_text,
    in_scope,
    reason_text,
)
from app.features.channels.ports import ChannelsStore, ChannelsUnitOfWork
from app.schemas.common import ErrorCode

type Clock = Callable[[], datetime]

CHANNELS_PATH = "/free-channels"


def system_clock() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True, slots=True)
class ChannelView:
    channel: FreeChannel
    my_role: MemberRole | None


@dataclass(frozen=True, slots=True)
class ChannelPage:
    items: list[ChannelView]
    next_before: int | None


@dataclass(frozen=True, slots=True)
class MembershipResult:
    channel: ChannelView
    changed: bool


@dataclass(frozen=True, slots=True)
class LeaveResult:
    # Cleanup after scope revocation must not disclose current channel metadata.
    channel_id: UUID
    changed: bool


@dataclass(frozen=True, slots=True)
class RequestPage:
    items: list[OfficialChannelRequest]
    next_before: int | None


@dataclass(frozen=True, slots=True)
class Created[T]:
    value: T
    replayed: bool


def _forbidden() -> ApiError:
    return ApiError(ErrorCode.FORBIDDEN)


def _conflict() -> ApiError:
    return ApiError(ErrorCode.CONFLICT)


def _not_found() -> ApiError:
    return ApiError(ErrorCode.NOT_FOUND)


def _cursor(before: int | None) -> int | None:
    if before is not None and before < 1:
        raise ApiError(ErrorCode.VALIDATION)
    return before


class ChannelsService:
    def __init__(self, store: ChannelsStore, clock: Clock = system_clock) -> None:
        self.store = store
        self.clock = clock

    # ---- helpers -------------------------------------------------------------------------

    @staticmethod
    def _eligible(uow: ChannelsUnitOfWork, channel: FreeChannel) -> bool:
        return in_scope(
            uow.actor_id, uow.current_memberships(), channel.department_id, channel.grade
        )

    @staticmethod
    def _require_free(uow: ChannelsUnitOfWork, channel_id: UUID) -> None:
        # Authoritative default department/grade channels are never managed through this API.
        if uow.is_default_channel(channel_id):
            raise _forbidden()

    def _locked(self, uow: ChannelsUnitOfWork, channel_id: UUID, *, scope: bool) -> FreeChannel:
        """Lock in the global order scope -> channel and return the current channel row."""
        self._require_free(uow, channel_id)
        if scope:
            peek = uow.get_channel(channel_id)
            if peek is None:
                raise _not_found()
            uow.lock_scope(peek.department_id, peek.grade)
        channel = uow.lock_channel(channel_id)
        if channel is None:
            raise _not_found()
        return channel

    def _owned(self, uow: ChannelsUnitOfWork, channel: FreeChannel) -> None:
        if not self._eligible(uow, channel):
            raise _forbidden()
        mine = uow.my_membership(channel.id)
        # Ownership is the stored OWNER membership AND the channel owner column. Either alone is
        # not enough, so a stale row cannot grant management.
        if mine is None or mine.role is not MemberRole.OWNER or channel.owner_id != uow.actor_id:
            raise _forbidden()

    @staticmethod
    def _view(uow: ChannelsUnitOfWork, channel: FreeChannel) -> ChannelView:
        mine = uow.my_membership(channel.id)
        return ChannelView(channel, mine.role if mine else None)

    # ---- reads ---------------------------------------------------------------------------

    def list_department(
        self,
        actor: ChannelsActor,
        department_id: UUID,
        before: int | None,
        limit: int,
    ) -> ChannelPage:
        check_page_size(limit, PAGE_MAX)
        before = _cursor(before)
        with self.store.unit_of_work(actor.user_id) as uow:
            memberships = uow.current_memberships()
            campus_actor = CampusActor(actor.user_id, memberships)
            if not campus_policy.belongs_to_department(campus_actor, department_id):
                raise _forbidden()
            scopes: dict[tuple[UUID, int | None], None] = {(department_id, None): None}
            for m in memberships:
                if m.department_id == department_id and m.grade is not None:
                    scopes[(department_id, m.grade)] = None
            rows = uow.list_active(list(scopes), before, limit + 1)
            page = rows[:limit]
            roles = uow.my_roles([row.id for row in page])
            items = [
                ChannelView(row, roles[row.id].role if row.id in roles else None) for row in page
            ]
            next_before = page[-1].seq if len(rows) > limit and page else None
            return ChannelPage(items, next_before)

    def my_channels(self, actor: ChannelsActor, before: int | None, limit: int) -> ChannelPage:
        check_page_size(limit, PAGE_MAX)
        before = _cursor(before)
        with self.store.unit_of_work(actor.user_id) as uow:
            rows = uow.my_channels(before, limit + 1)
            page = rows[:limit]
            roles = uow.my_roles([row.id for row in page])
            # Revocation: a stored membership is hidden once the current academic membership no
            # longer covers the channel scope. The cursor still advances past hidden rows.
            items = [
                ChannelView(row, roles[row.id].role)
                for row in page
                if row.id in roles and self._eligible(uow, row)
            ]
            next_before = page[-1].seq if len(rows) > limit and page else None
            return ChannelPage(items, next_before)

    def get(self, actor: ChannelsActor, channel_id: UUID) -> ChannelView:
        with self.store.unit_of_work(actor.user_id) as uow:
            self._require_free(uow, channel_id)
            channel = uow.get_channel(channel_id)
            if channel is None:
                raise _not_found()
            if not self._eligible(uow, channel):
                raise _forbidden()
            return self._view(uow, channel)

    # ---- channel lifecycle ---------------------------------------------------------------

    def create(
        self,
        actor: ChannelsActor,
        department_id: UUID,
        grade: int | None,
        name: str,
        description: str,
        key: str,
    ) -> Created[ChannelView]:
        display, name_key = channel_name(name)
        text = description_text(description)
        payload = {
            "department_id": str(department_id),
            "grade": grade,
            "name": display,
            "description": text,
        }
        new_id = uuid4()
        claim = claim_for(actor.user_id, CHANNELS_PATH, key, payload, new_id)
        with self.store.unit_of_work(actor.user_id) as uow:
            uow.lock_scope(department_id, grade)
            if not in_scope(actor.user_id, uow.current_memberships(), department_id, grade):
                raise _forbidden()
            existing = replayed_resource(uow.find_claim(claim.namespace), claim)
            if existing is not None:
                channel = uow.get_channel(existing)
                if channel is None:
                    raise _not_found()
                return Created(self._view(uow, channel), True)
            if uow.active_name_taken(department_id, grade, name_key, None):
                raise _conflict()
            if uow.count_owned_active(department_id, grade) >= OWNED_ACTIVE_LIMIT_PER_SCOPE:
                raise _conflict()
            now = self.clock()
            row = FreeChannel(
                id=new_id,
                department_id=department_id,
                grade=grade,
                name=display,
                name_key=name_key,
                description=text,
                owner_id=actor.user_id,
                status=ChannelStatus.ACTIVE,
                revision=1,
                created_at=now,
                updated_at=now,
            )
            owner = ChannelMembership(new_id, actor.user_id, MemberRole.OWNER, now)
            stored = uow.insert_channel(row, owner, claim)
            return Created(ChannelView(stored, MemberRole.OWNER), False)

    def update(
        self,
        actor: ChannelsActor,
        channel_id: UUID,
        name: str,
        description: str,
        expected_revision: int,
    ) -> ChannelView:
        display, name_key = channel_name(name)
        text = description_text(description)
        with self.store.unit_of_work(actor.user_id) as uow:
            channel = self._locked(uow, channel_id, scope=True)
            self._owned(uow, channel)
            if channel.status is not ChannelStatus.ACTIVE:
                raise _conflict()
            if channel.revision != expected_revision:
                raise _conflict()
            if uow.active_name_taken(channel.department_id, channel.grade, name_key, channel.id):
                raise _conflict()
            row = replace(
                channel,
                name=display,
                name_key=name_key,
                description=text,
                revision=channel.revision + 1,
                updated_at=self.clock(),
            )
            uow.update_channel(row, expected_revision)
            return ChannelView(row, MemberRole.OWNER)

    def archive(
        self, actor: ChannelsActor, channel_id: UUID, expected_revision: int
    ) -> ChannelView:
        with self.store.unit_of_work(actor.user_id) as uow:
            channel = self._locked(uow, channel_id, scope=True)
            self._owned(uow, channel)
            if channel.status is ChannelStatus.ARCHIVED:
                # Retry of the archive this revision produced: report the stored state.
                if channel.revision == expected_revision + 1:
                    return ChannelView(channel, MemberRole.OWNER)
                raise _conflict()
            if channel.revision != expected_revision:
                raise _conflict()
            now = self.clock()
            row = replace(
                channel,
                status=ChannelStatus.ARCHIVED,
                revision=channel.revision + 1,
                updated_at=now,
                archived_at=now,
            )
            uow.update_channel(row, expected_revision)
            pending = uow.pending_request(channel.id)
            if pending is not None:
                uow.update_request(
                    replace(
                        pending,
                        status=RequestStatus.CANCELLED,
                        revision=pending.revision + 1,
                        updated_at=now,
                    ),
                    pending.revision,
                )
            return ChannelView(row, MemberRole.OWNER)

    # ---- own membership ------------------------------------------------------------------

    def join(self, actor: ChannelsActor, channel_id: UUID) -> MembershipResult:
        with self.store.unit_of_work(actor.user_id) as uow:
            channel = self._locked(uow, channel_id, scope=False)
            if not self._eligible(uow, channel):
                raise _forbidden()
            mine = uow.my_membership(channel.id)
            if mine is not None:
                return MembershipResult(ChannelView(channel, mine.role), False)
            if channel.status is not ChannelStatus.ACTIVE:
                raise _conflict()
            if channel.member_count >= MEMBER_LIMIT:
                raise _conflict()
            uow.insert_membership(
                ChannelMembership(channel.id, actor.user_id, MemberRole.MEMBER, self.clock())
            )
            joined = replace(channel, member_count=channel.member_count + 1)
            return MembershipResult(ChannelView(joined, MemberRole.MEMBER), True)

    def leave(self, actor: ChannelsActor, channel_id: UUID) -> LeaveResult:
        # Leaving only removes the actor's own row, so it needs no current eligibility: a user
        # whose department changed can still clean up. It reveals nothing beyond 404/own state.
        with self.store.unit_of_work(actor.user_id) as uow:
            channel = self._locked(uow, channel_id, scope=False)
            mine = uow.my_membership(channel.id)
            if mine is None:
                if not self._eligible(uow, channel):
                    raise _forbidden()
                return LeaveResult(channel_id, False)
            if mine.role is MemberRole.OWNER:
                # Owners archive instead; ownership transfer is not in this pass.
                raise _conflict()
            uow.delete_my_membership(channel.id)
            return LeaveResult(channel_id, True)

    # ---- official channel requests (submission + own status only) ------------------------

    def request_official(
        self, actor: ChannelsActor, channel_id: UUID, reason: str, key: str
    ) -> Created[OfficialChannelRequest]:
        text = reason_text(reason)
        new_id = uuid4()
        claim = claim_for(
            actor.user_id,
            f"{CHANNELS_PATH}/{channel_id}/official-requests",
            key,
            {"reason": text},
            new_id,
        )
        with self.store.unit_of_work(actor.user_id) as uow:
            channel = self._locked(uow, channel_id, scope=False)
            self._owned(uow, channel)
            existing = replayed_resource(uow.find_claim(claim.namespace), claim)
            if existing is not None:
                stored = uow.get_request(existing)
                if stored is None or stored.requester_id != actor.user_id:
                    raise _not_found()
                return Created(stored, True)
            if channel.status is not ChannelStatus.ACTIVE:
                raise _conflict()
            if uow.pending_request(channel.id) is not None:
                raise _conflict()
            now = self.clock()
            row = OfficialChannelRequest(
                id=new_id,
                channel_id=channel.id,
                requester_id=actor.user_id,
                reason=text,
                status=RequestStatus.PENDING,
                revision=1,
                created_at=now,
                updated_at=now,
            )
            return Created(uow.insert_request(row, claim), False)

    def my_requests(self, actor: ChannelsActor, before: int | None, limit: int) -> RequestPage:
        check_page_size(limit, PAGE_MAX)
        before = _cursor(before)
        with self.store.unit_of_work(actor.user_id) as uow:
            rows = uow.my_requests(before, limit + 1)
            page = [row for row in rows[:limit] if row.requester_id == actor.user_id]
            next_before = rows[limit - 1].seq if len(rows) > limit else None
            return RequestPage(page, next_before)

    def get_request(self, actor: ChannelsActor, request_id: UUID) -> OfficialChannelRequest:
        with self.store.unit_of_work(actor.user_id) as uow:
            row = uow.get_request(request_id)
            # Another user's request is indistinguishable from a missing one.
            if row is None or row.requester_id != actor.user_id:
                raise _not_found()
            return row
