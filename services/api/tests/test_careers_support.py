"""Test-only in-memory fakes for the API-JOB Protocols. Never a production persistence layer.

`FakeUnitOfWork` serialises transactions with one lock and restores a snapshot on exception.
`ScopedLockUnitOfWork` runs transactions independently and only serialises through the
actor/program locks the service asks for, so it can expose a missing or misordered lock.
Both simulate the documented contract; neither is evidence of MariaDB isolation behaviour.
"""

import copy
import itertools
import threading
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from app.features.careers.domain import (
    ApplicationStatus,
    CareerGrant,
    CareersActor,
    DemoCareerPolicy,
)
from app.features.careers.ports import (
    ApplicationRecord,
    ClaimScope,
    EmployerDraftRecord,
    IdempotencyClaim,
    ProfileRecord,
    ProgramRecord,
    StoreBusy,
    StoreConflict,
)

NOW = datetime(2026, 10, 30, 3, 0, tzinfo=UTC)
USER_A = UUID("00000000-0000-4000-8000-00000000000a")
USER_B = UUID("00000000-0000-4000-8000-00000000000b")
ALL_STUDENT = frozenset({CareerGrant.PROFILE_SELF, CareerGrant.PROGRAM_APPLY_SELF})


def demo_policy(**overrides) -> DemoCareerPolicy:
    values = dict(
        policy_id="demo-careers-20261030",
        max_active_applications_per_user=3,
        enforce_program_window=True,
        allow_cancel_after_window=False,
        link_closed_contests=False,
        max_employer_drafts_per_actor=5,
    )
    values.update(overrides)
    return DemoCareerPolicy(**values)


def actor(user: UUID = USER_A) -> CareersActor:
    return CareersActor(user_id=user)


def make_program(**overrides) -> ProgramRecord:
    values = dict(
        id=uuid4(),
        title="[DEMO] 가상 취업 역량 캠프",
        host="가상 진로지원팀",
        summary="시연용 가상 프로그램",
        official=False,
        published=True,
        capacity=2,
        apply_starts_at=NOW - timedelta(days=1),
        apply_ends_at=NOW + timedelta(days=7),
    )
    values.update(overrides)
    return ProgramRecord(**values)


class InjectedFailure(Exception):
    """Simulated failure inside the transaction (e.g. claim insert or audit write)."""


class FakeUnitOfWork:
    def __init__(self, programs: list[ProgramRecord] | None = None):
        self.lock = threading.Lock()
        self.grant_map: dict[UUID, frozenset[CareerGrant]] = {}
        self.claims: dict[ClaimScope, IdempotencyClaim] = {}
        self.profiles: dict[UUID, ProfileRecord] = {}
        self.programs: dict[UUID, ProgramRecord] = {p.id: p for p in programs or []}
        self.applications: dict[UUID, ApplicationRecord] = {}
        self.drafts: dict[UUID, EmployerDraftRecord] = {}
        self.fail_put_claim = False
        self.transactions = 0

    def grant(self, user: UUID, *grants: CareerGrant) -> None:
        self.grant_map[user] = frozenset(grants)

    _STATE = ("grant_map", "claims", "profiles", "programs", "applications", "drafts")

    @contextmanager
    def transaction(self):
        with self.lock:
            self.transactions += 1
            snapshot = {name: copy.copy(getattr(self, name)) for name in self._STATE}
            try:
                yield FakeTransaction(self)
            except BaseException:
                for name, value in snapshot.items():
                    setattr(self, name, value)
                raise


class FakeTransaction:
    def __init__(self, uow: FakeUnitOfWork):
        self.u = uow

    def grants(self, user_id):
        return self.u.grant_map.get(user_id, frozenset())

    def find_claim(self, scope):
        return self.u.claims.get(scope)

    def put_claim(self, claim):
        if self.u.fail_put_claim:
            raise InjectedFailure()
        if claim.scope in self.u.claims:
            raise StoreConflict()
        self.u.claims[claim.scope] = claim

    def lock_actor(self, user_id):
        del user_id  # the global lock already serialises

    # profiles
    def get_profile(self, user_id):
        return next((p for p in self.u.profiles.values() if p.user_id == user_id), None)

    def get_profile_by_id(self, profile_id):
        return self.u.profiles.get(profile_id)

    def insert_profile(self, record):
        if self.get_profile(record.user_id) is not None:
            raise StoreConflict()
        self.u.profiles[record.id] = record

    def update_profile(self, record, expected_revision):
        current = self.u.profiles.get(record.id)
        if current is None or current.revision != expected_revision:
            return False
        self.u.profiles[record.id] = record
        return True

    def delete_profile(self, user_id, profile_id, expected_revision):
        current = self.u.profiles.get(profile_id)
        if current is None or current.user_id != user_id or current.revision != expected_revision:
            return False
        del self.u.profiles[profile_id]  # claims are kept as tombstones
        return True

    # programs
    def list_programs(self):
        return list(self.u.programs.values())

    def get_program(self, program_id):
        return self.u.programs.get(program_id)

    def lock_program(self, program_id):
        return self.u.programs.get(program_id)  # the global lock already serialises

    def _active(self):
        return [a for a in self.u.applications.values() if a.status is ApplicationStatus.APPLIED]

    def count_active_for_program(self, program_id):
        return sum(1 for a in self._active() if a.program_id == program_id)

    def count_active_for_user(self, user_id):
        return sum(1 for a in self._active() if a.user_id == user_id)

    def find_active_application(self, user_id, program_id):
        return next(
            (a for a in self._active() if a.user_id == user_id and a.program_id == program_id),
            None,
        )

    def get_application(self, application_id):
        return self.u.applications.get(application_id)

    def list_applications(self, user_id):
        return [a for a in self.u.applications.values() if a.user_id == user_id]

    def insert_application(self, record):
        if self.find_active_application(record.user_id, record.program_id) is not None:
            raise StoreConflict()
        self.u.applications[record.id] = record

    def update_application(self, record, expected_revision):
        current = self.u.applications.get(record.id)
        if current is None or current.revision != expected_revision:
            return False
        self.u.applications[record.id] = record
        return True

    # employer drafts
    def list_employer_drafts(self, owner_id):
        return [d for d in self.u.drafts.values() if d.owner_id == owner_id]

    def get_employer_draft(self, draft_id):
        return self.u.drafts.get(draft_id)

    def insert_employer_draft(self, record):
        self.u.drafts[record.id] = record

    def update_employer_draft(self, record, expected_revision):
        current = self.u.drafts.get(record.id)
        if current is None or current.revision != expected_revision:
            return False
        self.u.drafts[record.id] = record
        return True

    def delete_employer_draft(self, owner_id, draft_id, expected_revision):
        current = self.u.drafts.get(draft_id)
        if current is None or current.owner_id != owner_id or current.revision != expected_revision:
            return False
        del self.u.drafts[draft_id]
        return True


_DELETED = object()


class _Tracked(dict):
    """A table view that records this transaction's writes so commit can publish them."""

    def __init__(self, rows, dirty):
        super().__init__(rows)
        self._dirty = dirty

    def __setitem__(self, key, value):
        super().__setitem__(key, value)
        self._dirty[key] = value

    def __delitem__(self, key):
        super().__delitem__(key)
        self._dirty[key] = _DELETED


class _View:
    pass


class ScopedLockUnitOfWork:
    """Independent transactions guarded only by per-key locks (no global serialisation).

    Writes stay private to the transaction until commit; locks are held until commit/rollback.
    `read_committed=True` makes every read see the latest committed rows (the visibility the
    ports contract requires after a lock). `read_committed=False` freezes the view at the
    transaction's first read, like a plain SELECT under REPEATABLE READ, and `actor_locks=False`
    turns `lock_actor` into a no-op; both exist only as negative controls proving the race
    tests can fail. This is a model of the contract, not evidence of MariaDB behaviour.
    """

    _STATE = FakeUnitOfWork._STATE

    def __init__(
        self,
        programs: list[ProgramRecord] | None = None,
        *,
        actor_locks: bool = True,
        read_committed: bool = True,
        lock_timeout: float = 5.0,
    ):
        self.mutex = threading.Lock()
        self.grant_map: dict[UUID, frozenset[CareerGrant]] = {}
        self.claims: dict[ClaimScope, IdempotencyClaim] = {}
        self.profiles: dict[UUID, ProfileRecord] = {}
        self.programs: dict[UUID, ProgramRecord] = {p.id: p for p in programs or []}
        self.applications: dict[UUID, ApplicationRecord] = {}
        self.drafts: dict[UUID, EmployerDraftRecord] = {}
        self.actor_locks = actor_locks
        self.read_committed = read_committed
        self.lock_timeout = lock_timeout
        self.hooks: dict[str, Callable[[int], None]] = {}
        self.busy_failures = 0
        self.events: list[tuple[int, str]] = []
        self.transactions = 0
        self._locks: dict[tuple[str, UUID], threading.Lock] = {}
        self._ids = itertools.count(1)

    def grant(self, user: UUID, *grants: CareerGrant) -> None:
        with self.mutex:
            self.grant_map[user] = frozenset(grants)

    def log(self, tx_id: int, event: str) -> None:
        with self.mutex:
            self.events.append((tx_id, event))

    def events_of(self, tx_id: int) -> list[str]:
        with self.mutex:
            return [event for tid, event in self.events if tid == tx_id]

    def key_lock(self, kind: str, key: UUID) -> threading.Lock:
        with self.mutex:
            return self._locks.setdefault((kind, key), threading.Lock())

    def committed(self) -> dict[str, dict]:
        with self.mutex:
            return {name: dict(getattr(self, name)) for name in self._STATE}

    def hook(self, name: str, tx_id: int) -> None:
        if (callback := self.hooks.get(name)) is not None:
            callback(tx_id)

    def new_transaction(self, tx_id: int) -> "ScopedTransaction":
        return ScopedTransaction(self, tx_id)

    @contextmanager
    def transaction(self):
        with self.mutex:
            self.transactions += 1
        tx = self.new_transaction(next(self._ids))
        try:
            yield tx
            tx.commit()
        finally:
            tx.release()


class ScopedTransaction(FakeTransaction):
    def __init__(self, uow: ScopedLockUnitOfWork, tx_id: int):  # no super(): `u` is a view
        self.uow = uow
        self.id = tx_id
        self.held: list[threading.Lock] = []
        self.locked: set[tuple[str, UUID]] = set()
        self.dirty: dict[str, dict] = {name: {} for name in uow._STATE}
        self._snapshot: dict[str, dict] | None = None

    @property
    def u(self):
        if self.uow.read_committed or self._snapshot is None:
            self._snapshot = self.uow.committed()
        view = _View()
        for name, rows in self._snapshot.items():
            merged = dict(rows)
            for key, value in self.dirty[name].items():
                if value is _DELETED:
                    merged.pop(key, None)
                else:
                    merged[key] = value
            setattr(view, name, _Tracked(merged, self.dirty[name]))
        return view

    def _acquire(self, kind: str, key: UUID) -> None:
        if (kind, key) in self.locked:
            return
        with self.uow.mutex:
            busy = self.uow.busy_failures > 0
            if busy:
                self.uow.busy_failures -= 1
        if busy:
            raise StoreBusy()  # simulated deadlock victim
        self.uow.log(self.id, f"wait_{kind}")
        lock = self.uow.key_lock(kind, key)
        if not lock.acquire(timeout=self.uow.lock_timeout):
            raise StoreBusy()  # simulated lock-wait timeout
        self.held.append(lock)
        self.locked.add((kind, key))
        self.uow.log(self.id, f"lock_{kind}")

    def lock_actor(self, user_id):
        if self.uow.actor_locks:
            self._acquire("actor", user_id)
        self.uow.hook("after_lock_actor", self.id)

    def lock_program(self, program_id):
        self._acquire("program", program_id)
        return super().lock_program(program_id)

    def grants(self, user_id):
        self.uow.log(self.id, "grants")
        return super().grants(user_id)

    def find_claim(self, scope):
        self.uow.log(self.id, "find_claim")
        return super().find_claim(scope)

    def put_claim(self, claim):
        if claim.scope in self.u.claims:
            raise StoreConflict()
        self.u.claims[claim.scope] = claim

    def count_active_for_user(self, user_id):
        self.uow.log(self.id, "count_user")
        return super().count_active_for_user(user_id)

    def count_active_for_program(self, program_id):
        self.uow.log(self.id, "count_program")
        return super().count_active_for_program(program_id)

    def list_employer_drafts(self, owner_id):
        self.uow.log(self.id, "list_drafts")
        return super().list_employer_drafts(owner_id)

    def insert_application(self, record):
        self.uow.hook("before_insert", self.id)
        super().insert_application(record)

    def insert_employer_draft(self, record):
        self.uow.hook("before_insert", self.id)
        super().insert_employer_draft(record)

    def commit(self) -> None:
        with self.uow.mutex:
            for name, writes in self.dirty.items():
                table = getattr(self.uow, name)
                for key, value in writes.items():
                    if value is _DELETED:
                        table.pop(key, None)
                    else:
                        table[key] = value

    def release(self) -> None:
        while self.held:
            self.held.pop().release()


def rendezvous(parties: int, timeout: float) -> Callable[[int], None]:
    """Hook that waits for `parties` transactions; if one is blocked on a lock it gives up
    after `timeout` so the lock holder can commit."""
    barrier = threading.Barrier(parties)

    def wait(tx_id: int) -> None:
        del tx_id
        try:
            barrier.wait(timeout)
        except threading.BrokenBarrierError:
            pass

    return wait


def bump_revision(uow: FakeUnitOfWork, profile_id: UUID) -> None:
    """Simulate a concurrent writer changing the row between read and CAS."""
    current = uow.profiles[profile_id]
    uow.profiles[profile_id] = replace(current, revision=current.revision + 1)
