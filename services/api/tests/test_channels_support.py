"""Test-only in-memory ChannelsStore. Serialized by one RLock with snapshot rollback.

This proves service decisions and lock-call order, NOT MariaDB/InnoDB locking or isolation.
"""

import copy
import threading
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from app.core.errors import ApiError
from app.features.campus.domain import Membership
from app.features.channels.domain import (
    ChannelMembership,
    ChannelsActor,
    ChannelStatus,
    FreeChannel,
    OfficialChannelRequest,
    RequestStatus,
)
from app.features.channels.service import ChannelsService
from app.schemas.common import ErrorCode

DEPT = UUID("00000000-0000-4000-8000-0000000000d1")
OTHER_DEPT = UUID("00000000-0000-4000-8000-0000000000d2")
DEFAULT_CHANNEL = UUID("00000000-0000-4000-8000-00000000c0de")

ALICE = ChannelsActor(UUID("00000000-0000-4000-8000-00000000a11c"))  # DEPT grade 2
BOB = ChannelsActor(UUID("00000000-0000-4000-8000-000000000b0b"))  # DEPT grade 2
CAROL = ChannelsActor(UUID("00000000-0000-4000-8000-0000000ca201"))  # DEPT grade 3
DAVE = ChannelsActor(UUID("00000000-0000-4000-8000-000000000da5"))  # OTHER_DEPT grade 2
NOBODY = ChannelsActor(UUID("00000000-0000-4000-8000-000000000000"))  # no membership

KEY = "key-0000000000000001"
KEY2 = "key-0000000000000002"


class FakeClock:
    def __init__(self) -> None:
        self.now = datetime(2026, 10, 30, 9, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        self.now += timedelta(seconds=1)
        return self.now


class FakeChannelsStore:
    def __init__(self) -> None:
        self.lock = threading.RLock()
        self.memberships: dict[UUID, tuple[Membership, ...]] = {
            ALICE.user_id: (Membership(DEPT, 2),),
            BOB.user_id: (Membership(DEPT, 2),),
            CAROL.user_id: (Membership(DEPT, 3),),
            DAVE.user_id: (Membership(OTHER_DEPT, 2),),
        }
        self.default_channels = {DEFAULT_CHANNEL}
        self.channels: dict[UUID, FreeChannel] = {}
        self.members: dict[tuple[UUID, UUID], ChannelMembership] = {}
        self.requests: dict[UUID, OfficialChannelRequest] = {}
        self.claims: dict[tuple, object] = {}
        self.seq = 0
        self.ops: list[tuple] = []
        self.fail_after_write = False

    @contextmanager
    def unit_of_work(self, actor_id: UUID):
        with self.lock:
            snapshot = copy.deepcopy(
                (self.channels, self.members, self.requests, self.claims, self.seq)
            )
            self.ops.append(("begin", actor_id))
            try:
                yield FakeUow(self, actor_id)
                if self.fail_after_write:
                    raise RuntimeError("simulated commit failure")
            except BaseException:
                (self.channels, self.members, self.requests, self.claims, self.seq) = snapshot
                self.ops.append(("rollback", actor_id))
                raise
            self.ops.append(("commit", actor_id))

    def next_seq(self) -> int:
        self.seq += 1
        return self.seq

    def count(self, channel_id: UUID) -> int:
        return sum(1 for (cid, _) in self.members if cid == channel_id)


class FakeUow:
    def __init__(self, store: FakeChannelsStore, actor_id: UUID) -> None:
        self.s = store
        self.actor_id = actor_id

    def _row(self, channel: FreeChannel | None) -> FreeChannel | None:
        if channel is None:
            return None
        return copy.replace(channel, member_count=self.s.count(channel.id))

    def current_memberships(self):
        self.s.ops.append(("memberships",))
        return self.s.memberships.get(self.actor_id, ())

    def is_default_channel(self, channel_id):
        return channel_id in self.s.default_channels

    def find_claim(self, namespace):
        return self.s.claims.get(namespace)

    def lock_scope(self, department_id, grade):
        self.s.ops.append(("lock_scope", department_id, grade))

    def lock_channel(self, channel_id):
        self.s.ops.append(("lock_channel", channel_id))
        return self._row(self.s.channels.get(channel_id))

    def get_channel(self, channel_id):
        return self._row(self.s.channels.get(channel_id))

    def list_active(self, scopes, before_seq, limit):
        rows = [
            c
            for c in self.s.channels.values()
            if c.status is ChannelStatus.ACTIVE
            and (c.department_id, c.grade) in set(scopes)
            and (before_seq is None or c.seq < before_seq)
        ]
        rows.sort(key=lambda c: c.seq, reverse=True)
        return [self._row(c) for c in rows[:limit]]

    def active_name_taken(self, department_id, grade, name_key, exclude_id):
        self.s.ops.append(("name_check",))
        return any(
            c.status is ChannelStatus.ACTIVE
            and c.department_id == department_id
            and c.grade == grade
            and c.name_key == name_key
            and c.id != exclude_id
            for c in self.s.channels.values()
        )

    def count_owned_active(self, department_id, grade):
        return sum(
            1
            for c in self.s.channels.values()
            if c.status is ChannelStatus.ACTIVE
            and c.owner_id == self.actor_id
            and (c.department_id, c.grade) == (department_id, grade)
        )

    def insert_channel(self, row, owner, claim):
        assert owner.user_id == self.actor_id and claim.actor_id == self.actor_id
        if claim.namespace in self.s.claims:
            raise ApiError(ErrorCode.CONFLICT)
        stored = copy.replace(row, seq=self.s.next_seq())
        self.s.channels[row.id] = stored
        self.s.members[(row.id, owner.user_id)] = owner
        self.s.claims[claim.namespace] = claim
        return self._row(stored)

    def update_channel(self, row, expected_revision):
        current = self.s.channels[row.id]
        if current.revision != expected_revision:
            raise ApiError(ErrorCode.CONFLICT)
        self.s.channels[row.id] = copy.replace(row, seq=current.seq, member_count=0)

    def my_membership(self, channel_id):
        return self.s.members.get((channel_id, self.actor_id))

    def my_roles(self, channel_ids):
        return {
            cid: self.s.members[(cid, self.actor_id)]
            for cid in channel_ids
            if (cid, self.actor_id) in self.s.members
        }

    def my_channels(self, before_seq, limit):
        rows = [
            self.s.channels[cid]
            for (cid, uid) in self.s.members
            if uid == self.actor_id
            and (before_seq is None or self.s.channels[cid].seq < before_seq)
        ]
        rows.sort(key=lambda c: c.seq, reverse=True)
        return [self._row(c) for c in rows[:limit]]

    def insert_membership(self, row):
        assert row.user_id == self.actor_id
        key = (row.channel_id, row.user_id)
        if key in self.s.members:
            raise ApiError(ErrorCode.CONFLICT)
        self.s.members[key] = row

    def delete_my_membership(self, channel_id):
        del self.s.members[(channel_id, self.actor_id)]

    def pending_request(self, channel_id):
        return next(
            (
                r
                for r in self.s.requests.values()
                if r.channel_id == channel_id and r.status is RequestStatus.PENDING
            ),
            None,
        )

    def get_request(self, request_id):
        return self.s.requests.get(request_id)

    def my_requests(self, before_seq, limit):
        rows = [
            r
            for r in self.s.requests.values()
            if r.requester_id == self.actor_id and (before_seq is None or r.seq < before_seq)
        ]
        rows.sort(key=lambda r: r.seq, reverse=True)
        return rows[:limit]

    def insert_request(self, row, claim):
        if self.pending_request(row.channel_id) is not None:
            raise ApiError(ErrorCode.CONFLICT)
        stored = copy.replace(row, seq=self.s.next_seq())
        self.s.requests[row.id] = stored
        self.s.claims[claim.namespace] = claim
        return stored

    def update_request(self, row, expected_revision):
        if self.s.requests[row.id].revision != expected_revision:
            raise ApiError(ErrorCode.CONFLICT)
        self.s.requests[row.id] = row


def make() -> tuple[ChannelsService, FakeChannelsStore]:
    store = FakeChannelsStore()
    return ChannelsService(store, FakeClock()), store


def new_channel(service, actor=ALICE, name="알고리즘 스터디", grade=None, key=None):
    return service.create(actor, DEPT, grade, name, "주 1회 모임", key or f"key-{uuid4()}").value


def random_id() -> UUID:
    return uuid4()
