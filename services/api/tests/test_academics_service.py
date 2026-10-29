"""Academics service rules with the test-only fake unit of work.

TC-V1-ACA-003~009, TC-V1-ATT-001~002, TC-V1-X07(registration capacity), TC-V1-X09(demo labels).
The fake serializes units of work; real MariaDB locking/isolation is NOT_RUN.
"""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from uuid import uuid4

import pytest
from pydantic import ValidationError
from test_academics_support import (
    CODE,
    DEPT,
    GRADE_MINE,
    GRADE_OTHER,
    NOW,
    OFFERING_A,
    OFFERING_B,
    OFFERING_CLASH,
    OFFERING_FULL,
    OTHER,
    OTHER_REF,
    OTHER_TERM,
    OUTSIDER,
    STUDENT,
    STUDENT_REF,
    TEACHER,
    TERM,
    demo_policy,
    make_service,
    seeded_store,
)

from app.core.errors import ApiError
from app.features.academics.models import (
    AcademicActor,
    AttendanceGrant,
    CheckInInput,
    CorrectionInput,
    CorrectionResolve,
    EnrollInput,
    MarkInput,
    Provenance,
    RequestInput,
    RequestUpdate,
    RevisionInput,
    SessionInput,
    StudentStanding,
)
from app.features.academics.policy import BLOCKED_FLOWS, DemoAcademicPolicy, DemoWindow
from app.features.academics.service import AcademicsError
from app.schemas.common import ErrorCode

KEY = "key-0000000000000001"


def key(n: int) -> str:
    return f"key-{n:016d}"


@pytest.fixture
def store():
    return seeded_store()


@pytest.fixture
def service(store):
    return make_service(store)


def expect(code, callback, rule=None):
    with pytest.raises(ApiError) as exc:
        callback()
    assert exc.value.code == code
    if rule is not None:
        assert isinstance(exc.value, AcademicsError) and exc.value.rule == rule
    return exc.value


# -- policy / provenance ----------------------------------------------------------------------


def test_policy_requires_demo_label_and_aware_utc_windows():
    with pytest.raises(ValueError):
        DemoWindow(NOW.replace(tzinfo=None), NOW + timedelta(days=1))
    with pytest.raises(ValueError):
        DemoWindow(NOW, NOW)
    with pytest.raises(ValueError):
        demo_policy(label="2026 학사 규정")
    with pytest.raises(ValueError):
        demo_policy(max_credits_per_term=0)
    shifted = DemoWindow(NOW.astimezone(), NOW + timedelta(hours=1))
    assert shifted.opens_at.utcoffset() == timedelta(0)
    view = demo_policy().view()
    assert view.policy_source == "DEMO" and view.school_rules == "NOT_CONNECTED"
    assert set(BLOCKED_FLOWS) <= set(view.blocked)
    assert "BLUETOOTH_IDENTITY_CHECK" in view.blocked


def test_missing_policy_fails_closed_for_every_policy_flow(store):
    service = make_service(store, policy=None)
    assert service.search_offerings(STUDENT, None, "", 10)  # catalog read needs no policy
    flows = [
        lambda: service.policy_view(STUDENT),
        lambda: service.enroll(STUDENT, EnrollInput(offering_id=OFFERING_A), KEY),
        lambda: service.drop(STUDENT, uuid4(), RevisionInput(expected_revision=1)),
        lambda: service.create_request(
            STUDENT, RequestInput(kind="READMISSION", target_term_id=TERM, reason="r"), KEY
        ),
        lambda: service.open_session(TEACHER, OFFERING_A, SessionInput(label="1주"), KEY),
        lambda: service.check_in(
            STUDENT, OFFERING_A, uuid4(), CheckInInput(method="DEMO_CODE", code=CODE)
        ),
    ]
    for flow in flows:
        expect(ErrorCode.UNAVAILABLE, flow)
    assert store.data.enrollments == {} and store.data.claims == {}


def test_provenance_separates_official_demo_and_unknown():
    checked = NOW - timedelta(days=1)
    official = Provenance(
        source_kind="OFFICIAL_PUBLIC",
        source_url="https://www.dit.ac.kr/kr/index.php?pCode=classreginfo",
        checked_at=checked,
    )
    assert official.checked_at == checked
    for bad in (
        {"source_kind": "OFFICIAL_PUBLIC", "source_url": "https://www.dit.ac.kr/x"},
        {"source_kind": "OFFICIAL_PUBLIC", "checked_at": checked},
        {
            "source_kind": "OFFICIAL_PUBLIC",
            "source_url": "javascript:alert(1)",
            "checked_at": checked,
        },
        {
            "source_kind": "OFFICIAL_PUBLIC",
            "source_url": "http://www.dit.ac.kr/",
            "checked_at": checked,
        },
        {
            "source_kind": "OFFICIAL_PUBLIC",
            "source_url": "https://u:p@www.dit.ac.kr/",
            "checked_at": checked,
        },
        {"source_kind": "DEMO", "source_url": "https://www.dit.ac.kr/"},
        {"source_kind": "UNKNOWN", "checked_at": checked},
        {
            "source_kind": "OFFICIAL_PUBLIC",
            "source_url": "https://www.dit.ac.kr/",
            "checked_at": "2026-10-29T00:00:00",
        },
    ):
        with pytest.raises(ValidationError):
            Provenance(**bad)
    assert Provenance(source_kind="UNKNOWN").source_url is None


# -- FR-ACA-003 catalog -----------------------------------------------------------------------


def test_catalog_search_filters_and_hides_unknown(service):
    titles = {o.title for o in service.search_offerings(STUDENT, TERM, "가상", 25)}
    assert "가상 자료구조" in titles and len(titles) == 4
    assert service.search_offerings(STUDENT, OTHER_TERM, "", 25) == []
    assert [o.title for o in service.search_offerings(STUDENT, None, "웹", 25)] == ["가상 웹개발"]
    assert len(service.search_offerings(STUDENT, None, "", 1)) == 1
    expect(ErrorCode.NOT_FOUND, lambda: service.get_offering(STUDENT, uuid4()))
    detail = service.get_offering(STUDENT, OFFERING_A)
    assert detail.record_source == "DEMO" and detail.syllabus_source.source_kind == "DEMO"


# -- FR-ACA-004 registration ------------------------------------------------------------------


def test_enroll_replay_and_payload_mismatch(service, store):
    first = service.enroll(STUDENT, EnrollInput(offering_id=OFFERING_A), KEY)
    again = service.enroll(STUDENT, EnrollInput(offering_id=OFFERING_A), KEY)
    assert first.id == again.id and len(store.data.enrollments) == 1
    expect(
        ErrorCode.CONFLICT,
        lambda: service.enroll(STUDENT, EnrollInput(offering_id=OFFERING_B), KEY),
    )
    # Same key from another actor is a separate namespace, never a replay of STUDENT's row.
    other = service.enroll(OTHER, EnrollInput(offering_id=OFFERING_A), KEY)
    assert other.id != first.id
    assert "student_id" not in first.model_dump_json()
    assert [e.id for e in service.my_enrollments(OTHER)] == [other.id]


def test_enroll_rules_time_credit_capacity_and_duplicates(store):
    service = make_service(store, policy=demo_policy(max_credits_per_term=5))
    service.enroll(STUDENT, EnrollInput(offering_id=OFFERING_A), key(1))
    expect(
        ErrorCode.CONFLICT,
        lambda: service.enroll(STUDENT, EnrollInput(offering_id=OFFERING_A), key(2)),
        "ALREADY_ENROLLED",
    )
    expect(
        ErrorCode.CONFLICT,
        lambda: service.enroll(STUDENT, EnrollInput(offering_id=OFFERING_CLASH), key(3)),
        "TIME_CONFLICT",
    )
    expect(
        ErrorCode.CONFLICT,
        lambda: service.enroll(STUDENT, EnrollInput(offering_id=OFFERING_B), key(4)),
        "CREDIT_LIMIT",
    )
    expect(
        ErrorCode.CONFLICT,
        lambda: service.enroll(OTHER, EnrollInput(offering_id=OFFERING_FULL), key(5)),
        "CAPACITY_FULL",
    )
    expect(
        ErrorCode.NOT_FOUND,
        lambda: service.enroll(STUDENT, EnrollInput(offering_id=uuid4()), key(6)),
    )
    assert store.data.claims.keys() == {(STUDENT.user_id, "POST", "/academics/enrollments", key(1))}


def test_enroll_window_is_half_open_utc(store):
    window = demo_policy().registration_windows[TERM]
    for now in (window.opens_at - timedelta(seconds=1), window.closes_at):
        service = make_service(store, now=now)
        expect(
            ErrorCode.CONFLICT,
            lambda s=service: s.enroll(STUDENT, EnrollInput(offering_id=OFFERING_A), KEY),
            "WINDOW_CLOSED",
        )
    assert make_service(store, now=window.opens_at).enroll(
        STUDENT, EnrollInput(offering_id=OFFERING_A), KEY
    )
    naive = make_service(store, now=NOW.replace(tzinfo=None))
    expect(
        ErrorCode.UNAVAILABLE, lambda: naive.enroll(OTHER, EnrollInput(offering_id=OFFERING_B), KEY)
    )
    no_term_policy = make_service(store, policy=demo_policy(registration_windows={}))
    expect(
        ErrorCode.UNAVAILABLE,
        lambda: no_term_policy.enroll(OTHER, EnrollInput(offering_id=OFFERING_B), key(9)),
    )


def test_current_eligibility_is_rechecked_even_on_replay(service, store):
    expect(
        ErrorCode.FORBIDDEN,
        lambda: service.enroll(OUTSIDER, EnrollInput(offering_id=OFFERING_A), KEY),
    )
    store.data.standings[OTHER.user_id] = StudentStanding(
        access_active=True, registration_term_ids=frozenset({OTHER_TERM})
    )
    expect(
        ErrorCode.FORBIDDEN,
        lambda: service.enroll(OTHER, EnrollInput(offering_id=OFFERING_A), KEY),
    )
    service.enroll(STUDENT, EnrollInput(offering_id=OFFERING_A), KEY)
    store.data.standings[STUDENT.user_id] = StudentStanding(access_active=False)
    expect(
        ErrorCode.FORBIDDEN,
        lambda: service.enroll(STUDENT, EnrollInput(offering_id=OFFERING_A), KEY),
    )
    expect(ErrorCode.FORBIDDEN, lambda: service.my_enrollments(STUDENT))
    expect(ErrorCode.FORBIDDEN, lambda: service.transcript(STUDENT))


def test_parallel_registration_never_exceeds_capacity(store):
    service = make_service(store)
    students = [AcademicActor(user_id=uuid4()) for _ in range(8)]
    for actor in students:
        store.data.standings[actor.user_id] = StudentStanding(
            access_active=True, registration_term_ids=frozenset({TERM})
        )

    def attempt(actor):
        try:
            return service.enroll(actor, EnrollInput(offering_id=OFFERING_A), KEY).status
        except AcademicsError as exc:
            return exc.rule

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(attempt, students))
    assert results.count("ENROLLED") == 2 and results.count("CAPACITY_FULL") == 6
    assert service.get_offering(STUDENT, OFFERING_A).enrolled_count == 2


def test_parallel_same_student_different_keys_enrolls_once(service, store):
    def attempt(n):
        try:
            return service.enroll(STUDENT, EnrollInput(offering_id=OFFERING_B), key(n)).status
        except AcademicsError as exc:
            return exc.rule

    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(attempt, range(6)))
    assert results.count("ENROLLED") == 1 and results.count("ALREADY_ENROLLED") == 5


def test_drop_cas_tombstone_and_seat_release(service, store):
    row = service.enroll(STUDENT, EnrollInput(offering_id=OFFERING_A), KEY)
    expect(
        ErrorCode.NOT_FOUND, lambda: service.drop(OTHER, row.id, RevisionInput(expected_revision=1))
    )
    expect(
        ErrorCode.CONFLICT,
        lambda: service.drop(STUDENT, row.id, RevisionInput(expected_revision=2)),
        "STALE_REVISION",
    )
    dropped = service.drop(STUDENT, row.id, RevisionInput(expected_revision=1))
    assert dropped.status == "DROPPED" and dropped.revision == 2 and dropped.dropped_at == NOW
    expect(
        ErrorCode.CONFLICT,
        lambda: service.drop(STUDENT, row.id, RevisionInput(expected_revision=2)),
        "INVALID_STATE",
    )
    # Replaying the original create returns the tombstone; it does not resurrect a seat.
    replay = service.enroll(STUDENT, EnrollInput(offering_id=OFFERING_A), KEY)
    assert replay.id == row.id and replay.status == "DROPPED"
    assert service.get_offering(STUDENT, OFFERING_A).enrolled_count == 0
    fresh = service.enroll(STUDENT, EnrollInput(offering_id=OFFERING_A), key(2))
    assert fresh.id != row.id and fresh.status == "ENROLLED"
    late = make_service(store, now=NOW + timedelta(days=2))
    expect(
        ErrorCode.CONFLICT,
        lambda: late.drop(STUDENT, fresh.id, RevisionInput(expected_revision=1)),
        "WINDOW_CLOSED",
    )


# -- FR-ACA-005 demo record -------------------------------------------------------------------


def test_transcript_is_own_demo_record_without_graduation_judgement(service):
    view = service.transcript(STUDENT)
    assert [g.id for g in view.grades] == [GRADE_MINE]
    assert view.listed_credit_total == 3
    assert view.graduation_judgement == "NOT_PROVIDED" and view.official_effect == "NONE"
    encoded = view.model_dump_json()
    assert str(GRADE_OTHER) not in encoded and str(STUDENT.user_id) not in encoded
    expect(ErrorCode.FORBIDDEN, lambda: service.transcript(OUTSIDER))


# -- FR-ACA-006~009 requests ------------------------------------------------------------------


def make_request(service, actor=STUDENT, k=KEY, **fields):
    body = {"kind": "LEAVE_OF_ABSENCE", "target_term_id": TERM, "reason": " 가상 사유 "} | fields
    return service.create_request(actor, RequestInput(**body), k)


def test_request_kinds_targets_and_reference_scope(service):
    kinds = [
        dict(kind="LEAVE_OF_ABSENCE", target_term_id=TERM),
        dict(kind="RETURN_FROM_LEAVE", target_term_id=TERM),
        dict(kind="READMISSION", target_term_id=OTHER_TERM),
        dict(kind="MAJOR_TRANSFER", target_department_id=DEPT, target_term_id=None),
        dict(kind="GRADE_CORRECTION", target_grade_id=GRADE_MINE, target_term_id=None),
    ]
    for n, fields in enumerate(kinds):
        row = make_request(service, k=key(n), **fields)
        assert row.status == "DRAFT" and row.reason == "가상 사유"
        assert row.review_state == "NOT_CONNECTED" and row.official_effect == "NONE"
    with pytest.raises(ValidationError):
        RequestInput(kind="MAJOR_TRANSFER", target_term_id=TERM, reason="r")
    with pytest.raises(ValidationError):
        RequestInput(kind="GRADE_CORRECTION", reason="r")
    with pytest.raises(ValidationError):
        RequestInput(kind="READMISSION", target_term_id=TERM, reason="   ")
    for n, fields in enumerate(
        [
            # OTHER targeting STUDENT's grade must look exactly like a missing grade.
            dict(kind="GRADE_CORRECTION", target_grade_id=GRADE_MINE, target_term_id=None),
            dict(kind="MAJOR_TRANSFER", target_department_id=uuid4(), target_term_id=None),
            dict(kind="READMISSION", target_term_id=uuid4()),
        ]
    ):
        expect(
            ErrorCode.NOT_FOUND,
            lambda f=fields, n=n: make_request(service, OTHER, key(50 + n), **f),
        )


def test_request_duplicate_disabled_kind_and_replay(store, service):
    first = make_request(service)
    assert make_request(service).id == first.id
    expect(ErrorCode.CONFLICT, lambda: make_request(service, reason="다른 사유"))
    expect(ErrorCode.CONFLICT, lambda: make_request(service, k=key(2)), "ACTIVE_REQUEST_EXISTS")
    limited = make_service(store, policy=demo_policy(request_windows={}))
    expect(ErrorCode.UNAVAILABLE, lambda: make_request(limited, OTHER, key(3)))


def test_request_lifecycle_cas_window_and_tombstone(store, service):
    row = make_request(service)
    update = RequestUpdate(target_term_id=OTHER_TERM, reason="수정", expected_revision=1)
    changed = service.update_request(STUDENT, row.id, update)
    assert changed.revision == 2 and changed.target_term_id == OTHER_TERM
    expect(
        ErrorCode.CONFLICT,
        lambda: service.update_request(STUDENT, row.id, update),
        "STALE_REVISION",
    )
    expect(
        ErrorCode.VALIDATION,
        lambda: service.update_request(
            STUDENT,
            row.id,
            RequestUpdate(target_department_id=DEPT, reason="x", expected_revision=2),
        ),
    )
    late = make_service(store, now=NOW + timedelta(days=2))
    expect(
        ErrorCode.CONFLICT,
        lambda: late.submit_request(STUDENT, row.id, RevisionInput(expected_revision=2)),
        "WINDOW_CLOSED",
    )
    submitted = service.submit_request(STUDENT, row.id, RevisionInput(expected_revision=2))
    assert submitted.status == "SUBMITTED" and submitted.submitted_at == NOW
    expect(
        ErrorCode.CONFLICT,
        lambda: service.update_request(
            STUDENT, row.id, RequestUpdate(target_term_id=TERM, reason="x", expected_revision=3)
        ),
        "INVALID_STATE",
    )
    withdrawn = service.withdraw_request(STUDENT, row.id, RevisionInput(expected_revision=3))
    assert withdrawn.status == "WITHDRAWN" and withdrawn.reason is None
    assert make_request(service).status == "WITHDRAWN"  # replay keeps the tombstone
    assert [r.status for r in service.my_requests(STUDENT)] == ["WITHDRAWN"]
    expect(
        ErrorCode.CONFLICT,
        lambda: service.withdraw_request(STUDENT, row.id, RevisionInput(expected_revision=4)),
        "INVALID_STATE",
    )
    assert make_request(service, k=key(9)).status == "DRAFT"  # tombstone frees the active slot


def test_request_of_another_student_is_not_disclosed(service):
    row = make_request(service)
    for call in (
        lambda: service.submit_request(OTHER, row.id, RevisionInput(expected_revision=1)),
        lambda: service.withdraw_request(OTHER, row.id, RevisionInput(expected_revision=1)),
        lambda: service.update_request(
            OTHER, row.id, RequestUpdate(target_term_id=TERM, reason="x", expected_revision=1)
        ),
    ):
        expect(ErrorCode.NOT_FOUND, call)
    assert service.my_requests(OTHER) == []
    expect(ErrorCode.FORBIDDEN, lambda: service.my_requests(OUTSIDER))


def test_failed_unit_of_work_rolls_back_claim_and_row(store, service, monkeypatch):
    from test_academics_support import FakeUow

    original = FakeUow.insert_request

    def broken(self, row, claim):
        original(self, row, claim)
        raise RuntimeError("write failed after claim")

    monkeypatch.setattr(FakeUow, "insert_request", broken)
    with pytest.raises(RuntimeError):
        make_request(service)
    assert store.data.requests == {} and store.data.claims == {} and store.rollbacks == 1
    monkeypatch.setattr(FakeUow, "insert_request", original)
    assert make_request(service).status == "DRAFT"


# -- FR-ATT-001~002 attendance ----------------------------------------------------------------


def open_session(service, k=KEY):
    return service.open_session(TEACHER, OFFERING_A, SessionInput(label=" 1주차 "), k)


def check(service, actor=STUDENT, session_id=None, code=CODE):
    return service.check_in(
        actor, OFFERING_A, session_id, CheckInInput(method="DEMO_CODE", code=code)
    )


def test_session_open_roles_code_visibility_and_replay(service):
    session = open_session(service)
    assert session.check_in_code == CODE and session.label == "1주차"
    assert session.check_in_closes_at == NOW + timedelta(minutes=10)
    assert open_session(service).id == session.id
    expect(ErrorCode.CONFLICT, lambda: open_session(service, key(2)), "SESSION_ALREADY_OPEN")
    expect(
        ErrorCode.FORBIDDEN,
        lambda: service.open_session(STUDENT, OFFERING_A, SessionInput(label="x"), key(3)),
    )
    expect(
        ErrorCode.NOT_FOUND,
        lambda: service.open_session(OUTSIDER, OFFERING_A, SessionInput(label="x"), key(4)),
    )
    assert [s.check_in_code for s in service.sessions(STUDENT, OFFERING_A)] == [None]
    assert service.sessions(TEACHER, OFFERING_A)[0].check_in_code == CODE
    expect(ErrorCode.NOT_FOUND, lambda: service.sessions(OUTSIDER, OFFERING_A))
    assert [o.role for o in service.attendance_offerings(TEACHER, 25)] == ["teacher"]


def test_check_in_code_attempts_persist_and_limit(store, service):
    session = open_session(service)
    for _ in range(3):
        expect(
            ErrorCode.VALIDATION,
            lambda: check(service, session_id=session.id, code="000000"),
            "CODE_MISMATCH",
        )
    record = next(iter(store.data.records.values()))
    assert record.failed_attempts == 3 and record.mark == "UNMARKED"
    expect(ErrorCode.RATE_LIMITED, lambda: check(service, session_id=session.id), "ATTEMPT_LIMIT")
    ok = check(service, OTHER, session.id)
    assert (
        ok.mark == "CHECKED_IN" and ok.checked_in_at == NOW and ok.judgement == "DEMO_DISPLAY_ONLY"
    )
    assert check(service, OTHER, session.id).id == ok.id
    expect(ErrorCode.FORBIDDEN, lambda: check(service, TEACHER, session.id))
    expect(ErrorCode.NOT_FOUND, lambda: check(service, OUTSIDER, session.id))
    expect(ErrorCode.NOT_FOUND, lambda: check(service, session_id=uuid4()))
    with pytest.raises(ValidationError):
        CheckInInput(method="BLUETOOTH", code=CODE)


def test_check_in_window_and_closed_session(store, service):
    session = open_session(service)
    late = make_service(store, now=NOW + timedelta(minutes=10))
    expect(ErrorCode.CONFLICT, lambda: check(late, session_id=session.id), "SESSION_CLOSED")
    expect(
        ErrorCode.CONFLICT,
        lambda: service.close_session(
            TEACHER, OFFERING_A, session.id, RevisionInput(expected_revision=2)
        ),
        "STALE_REVISION",
    )
    closed = service.close_session(
        TEACHER, OFFERING_A, session.id, RevisionInput(expected_revision=1)
    )
    assert closed.status == "CLOSED"
    expect(ErrorCode.CONFLICT, lambda: check(service, session_id=session.id), "SESSION_CLOSED")
    expect(
        ErrorCode.FORBIDDEN,
        lambda: service.close_session(
            STUDENT, OFFERING_A, session.id, RevisionInput(expected_revision=2)
        ),
    )


def test_teacher_marks_with_cas_and_audit_history(store, service):
    session = open_session(service)
    check(service, session_id=session.id)
    rows = {r.member_ref: r for r in service.session_records(TEACHER, OFFERING_A, session.id)}
    assert rows[STUDENT_REF].mark == "CHECKED_IN" and rows[OTHER_REF].revision == 0
    assert rows[OTHER_REF].id is None
    marked = service.mark(
        TEACHER,
        OFFERING_A,
        session.id,
        STUDENT_REF,
        MarkInput(mark="LATE", reason="시연 수정", expected_revision=1),
    )
    assert marked.mark == "LATE" and marked.revision == 2
    expect(
        ErrorCode.CONFLICT,
        lambda: service.mark(
            TEACHER,
            OFFERING_A,
            session.id,
            STUDENT_REF,
            MarkInput(mark="PRESENT", reason="x", expected_revision=1),
        ),
        "STALE_REVISION",
    )
    absent = service.mark(
        TEACHER,
        OFFERING_A,
        session.id,
        OTHER_REF,
        MarkInput(mark="ABSENT", reason="미체크", expected_revision=0),
    )
    assert absent.revision == 1
    expect(
        ErrorCode.FORBIDDEN,
        lambda: service.mark(
            STUDENT,
            OFFERING_A,
            session.id,
            STUDENT_REF,
            MarkInput(mark="PRESENT", reason="x", expected_revision=2),
        ),
    )
    expect(
        ErrorCode.NOT_FOUND,
        lambda: service.mark(
            TEACHER,
            OFFERING_A,
            session.id,
            uuid4(),
            MarkInput(mark="PRESENT", reason="x", expected_revision=0),
        ),
    )
    history = service.record_history(TEACHER, OFFERING_A, marked.id)
    assert [(h.from_mark, h.to_mark, h.reason) for h in history] == [
        ("CHECKED_IN", "LATE", "시연 수정")
    ]
    assert str(TEACHER.user_id) not in history[0].model_dump_json()
    expect(ErrorCode.FORBIDDEN, lambda: service.record_history(STUDENT, OFFERING_A, marked.id))
    expect(ErrorCode.NOT_FOUND, lambda: service.record_history(TEACHER, OFFERING_A, uuid4()))
    store.data.grants[(TEACHER.user_id, OFFERING_A)] = AttendanceGrant(active=False, role="teacher")
    expect(
        ErrorCode.FORBIDDEN,
        lambda: service.mark(
            TEACHER,
            OFFERING_A,
            session.id,
            OTHER_REF,
            MarkInput(mark="PRESENT", reason="x", expected_revision=1),
        ),
    )


def test_student_sees_only_own_attendance(service):
    session = open_session(service)
    check(service, session_id=session.id)
    check(service, OTHER, session.id)
    mine = service.my_attendance(STUDENT, OFFERING_A)
    assert len(mine.records) == 1 and mine.records[0].is_mine
    assert mine.sessions[0].check_in_code is None
    assert mine.records[0].student_label is None and mine.records[0].member_ref is None
    expect(ErrorCode.FORBIDDEN, lambda: service.my_attendance(TEACHER, OFFERING_A))
    expect(ErrorCode.NOT_FOUND, lambda: service.my_attendance(OUTSIDER, OFFERING_A))
    expect(ErrorCode.FORBIDDEN, lambda: service.session_records(STUDENT, OFFERING_A, session.id))


def test_correction_request_resolution_and_revocation(store, service):
    session = open_session(service)
    mine = check(service, session_id=session.id)
    corr = CorrectionInput(requested_mark="PRESENT", reason="시연 정정 사유")
    expect(
        ErrorCode.CONFLICT,
        lambda: service.request_correction(STUDENT, OFFERING_A, mine.id, corr, KEY),
        "INVALID_STATE",
    )
    service.mark(
        TEACHER,
        OFFERING_A,
        session.id,
        STUDENT_REF,
        MarkInput(mark="ABSENT", reason="미확인", expected_revision=1),
    )
    other = check(service, OTHER, session.id)
    expect(
        ErrorCode.NOT_FOUND,
        lambda: service.request_correction(STUDENT, OFFERING_A, other.id, corr, key(2)),
    )
    created = service.request_correction(STUDENT, OFFERING_A, mine.id, corr, KEY)
    assert service.request_correction(STUDENT, OFFERING_A, mine.id, corr, KEY).id == created.id
    expect(
        ErrorCode.CONFLICT,
        lambda: service.request_correction(STUDENT, OFFERING_A, mine.id, corr, key(3)),
        "ACTIVE_REQUEST_EXISTS",
    )
    teacher_view = service.corrections(TEACHER, OFFERING_A)
    assert teacher_view[0].student_label == "가상 학생 1"
    expect(ErrorCode.FORBIDDEN, lambda: service.corrections(STUDENT, OFFERING_A))
    resolve = CorrectionResolve(decision="ACCEPTED", reason="확인", expected_revision=1)
    expect(
        ErrorCode.FORBIDDEN,
        lambda: service.resolve_correction(STUDENT, OFFERING_A, created.id, resolve),
    )
    done = service.resolve_correction(TEACHER, OFFERING_A, created.id, resolve)
    assert done.status == "ACCEPTED"
    assert service.my_attendance(STUDENT, OFFERING_A).records[0].mark == "PRESENT"
    history = service.record_history(TEACHER, OFFERING_A, mine.id)
    assert [h.to_mark for h in history] == ["ABSENT", "PRESENT"]
    expect(
        ErrorCode.CONFLICT,
        lambda: service.resolve_correction(TEACHER, OFFERING_A, created.id, resolve),
        "INVALID_STATE",
    )
    store.data.grants[(STUDENT.user_id, OFFERING_A)] = AttendanceGrant(active=False, role="student")
    expect(
        ErrorCode.FORBIDDEN,
        lambda: service.request_correction(STUDENT, OFFERING_A, mine.id, corr, KEY),
    )
    expect(ErrorCode.FORBIDDEN, lambda: service.my_attendance(STUDENT, OFFERING_A))
    assert service.attendance_offerings(STUDENT, 25) == []


def test_rejected_correction_keeps_mark(service):
    session = open_session(service)
    mine = check(service, session_id=session.id)
    service.mark(
        TEACHER,
        OFFERING_A,
        session.id,
        STUDENT_REF,
        MarkInput(mark="LATE", reason="r", expected_revision=1),
    )
    created = service.request_correction(
        STUDENT, OFFERING_A, mine.id, CorrectionInput(requested_mark="PRESENT", reason="r"), KEY
    )
    service.resolve_correction(
        TEACHER,
        OFFERING_A,
        created.id,
        CorrectionResolve(decision="REJECTED", reason="r", expected_revision=1),
    )
    assert service.my_attendance(STUDENT, OFFERING_A).records[0].mark == "LATE"


def test_parallel_teacher_marks_one_wins(service):
    session = open_session(service)

    def attempt(mark):
        try:
            return service.mark(
                TEACHER,
                OFFERING_A,
                session.id,
                OTHER_REF,
                MarkInput(mark=mark, reason="r", expected_revision=0),
            ).mark
        except AcademicsError as exc:
            return exc.rule

    with ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(attempt, ["PRESENT", "LATE", "ABSENT"]))
    assert results.count("STALE_REVISION") == 2


def test_policy_object_is_not_a_school_rule():
    policy = DemoAcademicPolicy(
        policy_id="p",
        label="demo",
        max_credits_per_term=1,
        check_in_window=timedelta(minutes=1),
        check_in_attempt_limit=1,
    )
    assert policy.registration_windows == {} and policy.view().school_rules == "NOT_CONNECTED"
    with pytest.raises(ValueError):
        DemoAcademicPolicy(
            policy_id="p",
            label="demo",
            max_credits_per_term=1,
            check_in_window=timedelta(days=2),
            check_in_attempt_limit=1,
        )
