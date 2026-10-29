"""M1: lock order and post-lock visibility against independent transactions (ScopedLockUnitOfWork).

Each race has a negative control (actor lock disabled / snapshot reads) showing the same
scenario does exceed the limit when the contract is not met, so a pass here is not just the
fake serialising everything. This models the ports contract; it does not verify MariaDB.
"""

import threading
import time
from uuid import UUID, uuid4

import pytest
from test_careers_support import (
    ALL_STUDENT,
    NOW,
    USER_A,
    USER_B,
    ScopedLockUnitOfWork,
    ScopedTransaction,
    actor,
    demo_policy,
    make_program,
    rendezvous,
)

from app.core.errors import ApiError
from app.features.careers import CareerGrant
from app.features.careers.domain import ApplicationStatus
from app.features.careers.ports import StoreBusy, StoreConflict
from app.features.careers.schemas import ApplicationCreate, EmployerDraftCreate, ProfileCreate
from app.features.careers.service import MAX_TX_ATTEMPTS, CareersService
from app.schemas.common import ErrorCode

# When one transaction is expected to block on a lock, the other gives up waiting at the
# rendezvous after BLOCKED_WAIT. When neither should block (negative controls, different actors)
# the generous ALL_ARRIVE wait keeps a slow machine from turning the race into a serial run.
BLOCKED_WAIT = 0.3
ALL_ARRIVE = 5.0


def service(uow, **policy) -> CareersService:
    return CareersService(demo_policy(**policy), uow=uow, clock=lambda: NOW)


def run_parallel(*calls) -> list[object]:
    outcomes: list[object] = [None] * len(calls)

    def run(index, call):
        try:
            call()
            outcomes[index] = "ok"
        except ApiError as exc:
            outcomes[index] = exc.code

    threads = [threading.Thread(target=run, args=(i, c)) for i, c in enumerate(calls)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)
    assert not any(thread.is_alive() for thread in threads)
    return outcomes


def active(uow: ScopedLockUnitOfWork) -> list:
    return [a for a in uow.applications.values() if a.status is ApplicationStatus.APPLIED]


def draft_body(**overrides) -> EmployerDraftCreate:
    values = dict(
        company_alias="가상기업",
        role_title="가상 백엔드 인턴",
        description="시연용 초안",
        employment_type="internship",
        closes_at=NOW.replace(year=2027),
    )
    values.update(overrides)
    return EmployerDraftCreate(**values)


def wait_for(predicate, timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while not predicate():
        assert time.monotonic() < deadline, "condition not reached"
        time.sleep(0.005)


# ------------------------------------------------------------ same actor, different programs


def two_programs_same_actor(*, actor_locks: bool):
    first, second = make_program(capacity=None), make_program(capacity=None)
    uow = ScopedLockUnitOfWork([first, second], actor_locks=actor_locks)
    uow.grant(USER_A, *ALL_STUDENT)
    uow.hooks["before_insert"] = rendezvous(2, BLOCKED_WAIT if actor_locks else ALL_ARRIVE)
    svc = service(uow, max_active_applications_per_user=1)
    outcomes = run_parallel(
        lambda: svc.apply(actor(), first.id, ApplicationCreate(), "key-a"),
        lambda: svc.apply(actor(), second.id, ApplicationCreate(), "key-b"),
    )
    return uow, outcomes


def test_per_user_limit_holds_across_different_programs():
    uow, outcomes = two_programs_same_actor(actor_locks=True)
    assert sorted(map(str, outcomes)) == sorted(["ok", str(ErrorCode.CONFLICT)])
    assert len(active(uow)) == 1


def test_negative_control_without_actor_lock_the_limit_is_exceeded():
    # Program locks alone do not serialise one actor across two programs.
    uow, outcomes = two_programs_same_actor(actor_locks=False)
    assert outcomes == ["ok", "ok"]
    assert len(active(uow)) == 2


# ------------------------------------------------------------ different actors, one program


def one_program_two_actors(*, read_committed: bool):
    program = make_program(capacity=1)
    uow = ScopedLockUnitOfWork([program], read_committed=read_committed)
    uow.grant(USER_A, *ALL_STUDENT)
    uow.grant(USER_B, *ALL_STUDENT)
    # Both transactions have read (and so taken a snapshot) before either locks the program.
    uow.hooks["after_lock_actor"] = rendezvous(2, ALL_ARRIVE)
    svc = service(uow)
    outcomes = run_parallel(
        lambda: svc.apply(actor(USER_A), program.id, ApplicationCreate(), "key-a"),
        lambda: svc.apply(actor(USER_B), program.id, ApplicationCreate(), "key-b"),
    )
    return uow, outcomes


def test_capacity_holds_when_post_lock_reads_see_committed_rows():
    uow, outcomes = one_program_two_actors(read_committed=True)
    assert sorted(map(str, outcomes)) == sorted(["ok", str(ErrorCode.CONFLICT)])
    assert len(active(uow)) == 1


def test_negative_control_snapshot_reads_after_the_lock_overrun_capacity():
    # The REPEATABLE READ hazard the ports contract forbids: lock granted, count still stale.
    uow, outcomes = one_program_two_actors(read_committed=False)
    assert outcomes == ["ok", "ok"]
    assert len(active(uow)) == 2


# ------------------------------------------------------------ employer draft limit


def test_employer_draft_limit_holds_under_concurrent_creates():
    drafter = uuid4()
    uow = ScopedLockUnitOfWork()
    uow.grant(drafter, CareerGrant.EMPLOYER_DRAFT)
    uow.hooks["before_insert"] = rendezvous(2, BLOCKED_WAIT)
    svc = service(uow, max_employer_drafts_per_actor=1)
    outcomes = run_parallel(
        lambda: svc.create_employer_draft(actor(drafter), draft_body(), "key-d1"),
        lambda: svc.create_employer_draft(actor(drafter), draft_body(), "key-d2"),
    )
    assert sorted(map(str, outcomes)) == sorted(["ok", str(ErrorCode.CONFLICT)])
    assert len(uow.drafts) == 1


# ------------------------------------------------------------ order and grant re-check


def test_lock_order_actor_then_program_and_grant_read_after_lock():
    program = make_program()
    uow = ScopedLockUnitOfWork([program])
    uow.grant(USER_A, *ALL_STUDENT)
    uow.grant(UUID(int=7), CareerGrant.EMPLOYER_DRAFT)
    svc = service(uow)
    applied, _ = svc.apply(actor(), program.id, ApplicationCreate(), "key-a")
    assert uow.events_of(1) == [
        "grants",
        "wait_actor",
        "lock_actor",
        "grants",
        "find_claim",
        "wait_program",
        "lock_program",
        "count_user",
        "count_program",
    ]
    svc.cancel_application(actor(), applied.id, applied.revision)
    assert uow.events_of(2) == [
        "grants",
        "wait_actor",
        "lock_actor",
        "grants",
        "wait_program",
        "lock_program",
    ]
    created, _ = svc.create_employer_draft(actor(UUID(int=7)), draft_body(), "key-d")
    assert uow.events_of(3)[:5] == ["grants", "wait_actor", "lock_actor", "grants", "find_claim"]
    svc.delete_employer_draft(actor(UUID(int=7)), created.id, created.revision)
    assert uow.events_of(4)[:4] == ["grants", "wait_actor", "lock_actor", "grants"]
    profile, _ = svc.create_profile(actor(), ProfileCreate(alias="별빛개발자"), "key-p")
    assert uow.events_of(5)[:5] == ["grants", "wait_actor", "lock_actor", "grants", "find_claim"]
    svc.delete_profile(actor(), profile.revision)
    assert uow.events_of(6)[:4] == ["grants", "wait_actor", "lock_actor", "grants"]


def test_grant_revoked_while_waiting_for_the_actor_lock_is_403():
    first, second = make_program(capacity=None), make_program(capacity=None)
    uow = ScopedLockUnitOfWork([first, second])
    uow.grant(USER_A, *ALL_STUDENT)
    release = threading.Event()
    uow.hooks["before_insert"] = lambda tx_id: release.wait(5) if tx_id == 1 else None
    svc = service(uow)
    results: dict[str, object] = {}

    def holder():
        svc.apply(actor(), first.id, ApplicationCreate(), "key-a")
        results["holder"] = "ok"

    def waiter():
        try:
            svc.apply(actor(), second.id, ApplicationCreate(), "key-b")
            results["waiter"] = "ok"
        except ApiError as exc:
            results["waiter"] = exc.code

    t1 = threading.Thread(target=holder)
    t1.start()
    wait_for(lambda: "lock_actor" in uow.events_of(1))
    t2 = threading.Thread(target=waiter)
    t2.start()
    wait_for(lambda: "wait_actor" in uow.events_of(2))  # passed the cheap check, now blocked
    uow.grant(USER_A, CareerGrant.PROFILE_SELF)  # revoke apply while tx 2 waits
    release.set()
    t1.join(5)
    t2.join(5)
    assert results == {"holder": "ok", "waiter": ErrorCode.FORBIDDEN}
    assert len(active(uow)) == 1


# ------------------------------------------------------------ deadlock / timeout / UNIQUE mapping


def test_deadlock_victim_is_retried_in_a_new_transaction():
    program = make_program()
    uow = ScopedLockUnitOfWork([program])
    uow.grant(USER_A, *ALL_STUDENT)
    uow.busy_failures = MAX_TX_ATTEMPTS - 1
    created, replayed = service(uow).apply(actor(), program.id, ApplicationCreate(), "key-a")
    assert replayed is False and created.status is ApplicationStatus.APPLIED
    assert uow.transactions == MAX_TX_ATTEMPTS and len(active(uow)) == 1


def test_retries_are_bounded_and_map_to_409_without_driver_detail():
    program = make_program()
    uow = ScopedLockUnitOfWork([program])
    uow.grant(USER_A, *ALL_STUDENT)
    uow.busy_failures = MAX_TX_ATTEMPTS
    with pytest.raises(ApiError) as excinfo:
        service(uow).apply(actor(), program.id, ApplicationCreate(), "key-a")
    assert excinfo.value.code is ErrorCode.CONFLICT
    assert excinfo.value.__cause__ is None and excinfo.value.__context__ is None
    assert uow.transactions == MAX_TX_ATTEMPTS and uow.applications == {}


def test_lock_wait_timeout_is_a_bounded_409():
    first, second = make_program(capacity=None), make_program(capacity=None)
    uow = ScopedLockUnitOfWork([first, second], lock_timeout=0.05)
    uow.grant(USER_A, *ALL_STUDENT)
    release = threading.Event()
    uow.hooks["before_insert"] = lambda tx_id: release.wait(5) if tx_id == 1 else None
    svc = service(uow)
    holder = threading.Thread(
        target=lambda: svc.apply(actor(), first.id, ApplicationCreate(), "key-a")
    )
    holder.start()
    wait_for(lambda: "lock_actor" in uow.events_of(1))
    try:
        with pytest.raises(ApiError) as excinfo:
            svc.apply(actor(), second.id, ApplicationCreate(), "key-b")
    finally:
        release.set()
        holder.join(5)
    assert excinfo.value.code is ErrorCode.CONFLICT
    assert uow.transactions == 1 + MAX_TX_ATTEMPTS
    assert len(active(uow)) == 1


class _ConflictingUpdate(ScopedLockUnitOfWork):
    """UNIQUE/CHECK violation on a non-idempotent write (e.g. cancel)."""

    def new_transaction(self, tx_id: int) -> ScopedTransaction:
        tx = super().new_transaction(tx_id)

        def update_application(record, expected_revision):
            raise StoreConflict("Duplicate entry 'secret' for key 'uq' (1062)")

        tx.update_application = update_application
        return tx


def test_store_conflict_on_cancel_is_409_and_not_retried():
    program = make_program()
    seed = ScopedLockUnitOfWork([program])
    seed.grant(USER_A, *ALL_STUDENT)
    created, _ = service(seed).apply(actor(), program.id, ApplicationCreate(), "key-a")
    uow = _ConflictingUpdate([program])
    uow.grant(USER_A, *ALL_STUDENT)
    uow.applications = dict(seed.applications)
    with pytest.raises(ApiError) as excinfo:
        service(uow).cancel_application(actor(), created.id, created.revision)
    assert excinfo.value.code is ErrorCode.CONFLICT
    assert "1062" not in str(excinfo.value) and "secret" not in str(excinfo.value)
    assert uow.transactions == 1
    assert next(iter(uow.applications.values())).status is ApplicationStatus.APPLIED


def test_store_busy_text_is_neither_chained_nor_repeated():
    # The adapter should raise StoreBusy without driver text; even if some slips through, the
    # 409 the service raises does not chain or repeat it.
    calls = []

    def always_busy():
        calls.append(1)
        raise StoreBusy("Deadlock found when trying to get lock (1213) secret-sql")

    with pytest.raises(ApiError) as excinfo:
        CareersService._run(always_busy)
    assert excinfo.value.code is ErrorCode.CONFLICT and len(calls) == MAX_TX_ATTEMPTS
    assert "1213" not in str(excinfo.value) and excinfo.value.__context__ is None
