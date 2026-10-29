"""Aggregate-lock races for academics with the test-only AggregateLockStore (no global lock).

Two units run concurrently and rendezvous before their first lock or aggregate read, so a flow
that reads an aggregate before locking it decides from stale state. This verifies that the
service takes the Protocol's aggregate locks in the documented order; it is NOT a MariaDB
concurrency or isolation test (real DB: NOT_RUN).
"""

from concurrent.futures import ThreadPoolExecutor
from threading import Thread
from uuid import uuid4

import pytest
from test_academics_support import (
    CODE,
    GRADE_MINE,
    OFFERING_A,
    OFFERING_B,
    OFFERING_CLASH,
    OTHER_TERM,
    STUDENT,
    STUDENT_REF,
    TEACHER,
    TERM,
    AggregateLockStore,
    demo_policy,
    make_service,
)

from app.core.errors import ApiError
from app.features.academics.models import (
    AcademicActor,
    AttendanceGrant,
    CheckInInput,
    CorrectionInput,
    EnrollInput,
    MarkInput,
    RequestInput,
    RequestUpdate,
    RevisionInput,
    SessionInput,
    StudentStanding,
)
from app.schemas.common import ErrorCode


def outcome(callback):
    try:
        return callback()
    except ApiError as exc:
        return getattr(exc, "rule", exc.code)


def race(store: AggregateLockStore, *callbacks):
    store.arm(len(callbacks))
    try:
        with ThreadPoolExecutor(max_workers=len(callbacks)) as pool:
            return [f.result() for f in [pool.submit(outcome, cb) for cb in callbacks]]
    finally:
        store.barrier = None


def active_enrollments(store):
    return [e for e in store.data.enrollments.values() if e.status == "ENROLLED"]


# -- registration aggregate(actor, term) -------------------------------------------------------


def test_parallel_enrollments_in_different_offerings_respect_credit_limit():
    store = AggregateLockStore()
    service = make_service(store, demo_policy(max_credits_per_term=3))
    results = race(
        store,
        lambda: service.enroll(STUDENT, EnrollInput(offering_id=OFFERING_A), "race-credit-0001"),
        lambda: service.enroll(STUDENT, EnrollInput(offering_id=OFFERING_B), "race-credit-0002"),
    )
    assert sorted(r if isinstance(r, str) else r.status for r in results) == [
        "CREDIT_LIMIT",
        "ENROLLED",
    ]
    rows = active_enrollments(store)
    assert len(rows) == 1 and sum(store.data.offerings[r.offering_id].credits for r in rows) <= 3
    assert store.rollbacks == 1


def test_parallel_enrollments_in_overlapping_offerings_keep_one():
    store = AggregateLockStore()
    service = make_service(store)
    results = race(
        store,
        lambda: service.enroll(STUDENT, EnrollInput(offering_id=OFFERING_A), "race-clash-0001"),
        lambda: service.enroll(STUDENT, EnrollInput(offering_id=OFFERING_CLASH), "race-clash-0002"),
    )
    assert sorted(r if isinstance(r, str) else r.status for r in results) == [
        "ENROLLED",
        "TIME_CONFLICT",
    ]
    assert len(active_enrollments(store)) == 1


def test_enroll_and_drop_lock_registration_before_reads_and_seats():
    store = AggregateLockStore()
    service = make_service(store)
    row = service.enroll(STUDENT, EnrollInput(offering_id=OFFERING_A), "order-enroll-0001")
    enroll_trace = [name for _, name in store.trace]
    store.trace.clear()
    service.drop(STUDENT, row.id, RevisionInput(expected_revision=1))
    drop_trace = [name for _, name in store.trace]

    def before(trace, first, then):
        return trace.index(first) < trace.index(then)

    assert before(enroll_trace, "lock:registration", "my_enrollments")
    assert before(enroll_trace, "lock:registration", "find_claim")
    assert before(enroll_trace, "lock:registration", "lock:seat")
    assert before(drop_trace, "lock:registration", "lock:seat")
    # drop re-reads the enrollment and standing after taking the aggregate lock
    after_lock = drop_trace[drop_trace.index("lock:registration") :]
    assert "get_my_enrollment" in after_lock and "standing" in after_lock


def test_standing_is_rechecked_after_waiting_for_the_registration_lock():
    store = AggregateLockStore()
    service = make_service(store)
    held = store.named_lock(("registration", STUDENT.user_id, TERM))
    held.acquire()
    result = {}
    worker = Thread(
        target=lambda: result.setdefault(
            "value",
            outcome(
                lambda: service.enroll(
                    STUDENT, EnrollInput(offering_id=OFFERING_A), "recheck-key-0001"
                )
            ),
        )
    )
    worker.start()
    assert store.waiting.wait(timeout=5)
    # Revoked while the request waits behind another registration transaction.
    store.data.standings[STUDENT.user_id] = StudentStanding(
        access_active=True, registration_term_ids=frozenset({OTHER_TERM})
    )
    held.release()
    worker.join(timeout=5)
    assert result["value"] == ErrorCode.FORBIDDEN
    assert active_enrollments(store) == []


# -- student request aggregate(actor) ----------------------------------------------------------


def leave_request(service, key):
    return service.create_request(
        STUDENT,
        RequestInput(kind="LEAVE_OF_ABSENCE", target_term_id=TERM, reason="가상 사유"),
        key,
    )


def active_requests(store, kind):
    return [
        r
        for r in store.data.requests.values()
        if r.kind == kind and r.status in {"DRAFT", "SUBMITTED"}
    ]


def test_parallel_requests_with_different_keys_create_one_active():
    store = AggregateLockStore()
    service = make_service(store)
    results = race(
        store,
        lambda: leave_request(service, "race-request-0001"),
        lambda: leave_request(service, "race-request-0002"),
    )
    assert sum(1 for r in results if r == "ACTIVE_REQUEST_EXISTS") == 1
    assert len(active_requests(store, "LEAVE_OF_ABSENCE")) == 1


def test_parallel_create_and_update_cannot_both_target_the_same_grade():
    store = AggregateLockStore()
    service = make_service(store)
    other_grade = uuid4()
    mine = next(g for g in store.data.grades if g.id == GRADE_MINE)
    store.data.grades.append(mine.model_copy(update={"id": other_grade}))
    draft = service.create_request(
        STUDENT,
        RequestInput(kind="GRADE_CORRECTION", target_grade_id=other_grade, reason="가상 사유"),
        "setup-draft-0001",
    )
    results = race(
        store,
        lambda: service.create_request(
            STUDENT,
            RequestInput(kind="GRADE_CORRECTION", target_grade_id=GRADE_MINE, reason="가상"),
            "race-grade-0001",
        ),
        lambda: service.update_request(
            STUDENT,
            draft.id,
            RequestUpdate(target_grade_id=GRADE_MINE, reason="가상", expected_revision=1),
        ),
    )
    assert sum(1 for r in results if r == "ACTIVE_REQUEST_EXISTS") == 1
    targeting = [
        r for r in active_requests(store, "GRADE_CORRECTION") if r.target_grade_id == GRADE_MINE
    ]
    assert len(targeting) == 1


# -- offering-session aggregate, session row, record row ---------------------------------------


@pytest.fixture
def attendance():
    store = AggregateLockStore()
    second = AcademicActor(user_id=uuid4())
    store.data.grants[(second.user_id, OFFERING_A)] = AttendanceGrant(active=True, role="teacher")
    return store, make_service(store), second


def test_two_teachers_cannot_open_two_sessions(attendance):
    store, service, second = attendance
    results = race(
        store,
        lambda: service.open_session(
            TEACHER, OFFERING_A, SessionInput(label="가상 1주차"), "race-session-0001"
        ),
        lambda: service.open_session(
            second, OFFERING_A, SessionInput(label="가상 1주차"), "race-session-0002"
        ),
    )
    assert results.count("SESSION_ALREADY_OPEN") == 1
    assert sum(1 for s in store.data.sessions.values() if s.status == "OPEN") == 1


def test_check_in_commits_before_close_or_sees_closed(attendance):
    store, service, _ = attendance
    opened = service.open_session(
        TEACHER, OFFERING_A, SessionInput(label="가상 1주차"), "setup-session-0001"
    )
    store.commit_log.clear()
    results = race(
        store,
        lambda: service.close_session(
            TEACHER, OFFERING_A, opened.id, RevisionInput(expected_revision=1)
        ),
        lambda: service.check_in(
            STUDENT, OFFERING_A, opened.id, CheckInInput(method="DEMO_CODE", code=CODE)
        ),
    )
    closed, checked = results
    assert closed.status == "CLOSED"
    if checked == "SESSION_CLOSED":
        assert store.commit_log == [TEACHER.user_id]
        assert not store.data.records
    else:
        assert checked.mark == "CHECKED_IN"
        # A successful check-in must be ordered before the close commit.
        assert store.commit_log == [STUDENT.user_id, TEACHER.user_id]


def test_parallel_corrections_for_one_record_keep_one_pending(attendance):
    store, service, _ = attendance
    opened = service.open_session(
        TEACHER, OFFERING_A, SessionInput(label="가상 1주차"), "setup-session-0002"
    )
    record = service.mark(
        TEACHER,
        OFFERING_A,
        opened.id,
        STUDENT_REF,
        MarkInput(mark="ABSENT", reason="가상", expected_revision=0),
    )
    results = race(
        store,
        *[
            (
                lambda n=n: service.request_correction(
                    STUDENT,
                    OFFERING_A,
                    record.id,
                    CorrectionInput(requested_mark="PRESENT", reason="가상"),
                    f"race-correction-{n:04d}",
                )
            )
            for n in range(2)
        ],
    )
    assert results.count("ACTIVE_REQUEST_EXISTS") == 1
    pending = [c for c in store.data.corrections.values() if c.status == "REQUESTED"]
    assert len(pending) == 1
