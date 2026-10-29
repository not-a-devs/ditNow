"""Test-only serialized in-memory unit of work for the academics feature.

This fake is never installed by application code. It models the Protocol contract (actor-bound
reads, CAS writes, claim+row in one unit, rollback on exception) so the service rules can be
tested. It does NOT prove MariaDB locking, isolation or persistence.
"""

import copy
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from threading import RLock
from uuid import UUID, uuid4

from app.core.errors import ApiError
from app.features.academics.models import (
    AcademicActor,
    AttendanceGrant,
    AttendanceOffering,
    GradeRecord,
    MeetingSlot,
    Offering,
    Provenance,
    RosterEntry,
    SeatState,
    StudentStanding,
)
from app.features.academics.policy import DemoAcademicPolicy, DemoWindow
from app.features.academics.service import AcademicsService
from app.schemas.common import ErrorCode

NOW = datetime(2026, 10, 30, 3, 0, tzinfo=UTC)
TERM, OTHER_TERM = uuid4(), uuid4()
DEPT = uuid4()
OFFERING_A, OFFERING_B, OFFERING_CLASH, OFFERING_FULL = (uuid4() for _ in range(4))
STUDENT, OTHER, TEACHER, OUTSIDER = (AcademicActor(user_id=uuid4()) for _ in range(4))
CODE = "123456"


def slot(weekday: int, start: int, end: int) -> MeetingSlot:
    return MeetingSlot(weekday=weekday, starts_minute=start, ends_minute=end)


def offering(id: UUID, title: str, credits: int, capacity: int, meetings) -> Offering:
    return Offering(
        id=id,
        term_id=TERM,
        course_code=f"DEMO-{title[:3]}",
        title=title,
        section="A",
        instructor_name="가상 교수",
        credits=credits,
        capacity=capacity,
        enrolled_count=0,
        meetings=meetings,
        syllabus_summary="가상 강의계획 요약",
        syllabus_source=Provenance(source_kind="DEMO"),
    )


def demo_policy(**overrides) -> DemoAcademicPolicy:
    window = DemoWindow(NOW - timedelta(days=1), NOW + timedelta(days=1))
    values = dict(
        policy_id="demo-2026",
        label="DEMO 시연 정책",
        max_credits_per_term=6,
        check_in_window=timedelta(minutes=10),
        check_in_attempt_limit=3,
        registration_windows={TERM: window},
        request_windows={
            kind: window
            for kind in (
                "LEAVE_OF_ABSENCE",
                "RETURN_FROM_LEAVE",
                "READMISSION",
                "MAJOR_TRANSFER",
                "GRADE_CORRECTION",
            )
        },
    )
    values.update(overrides)
    return DemoAcademicPolicy(**values)


@dataclass
class Data:
    claims: dict = field(default_factory=dict)
    standings: dict = field(default_factory=dict)
    terms: set = field(default_factory=set)
    departments: set = field(default_factory=set)
    offerings: dict = field(default_factory=dict)
    enrollments: dict = field(default_factory=dict)
    grades: list = field(default_factory=list)
    requests: dict = field(default_factory=dict)
    att_offerings: dict = field(default_factory=dict)
    grants: dict = field(default_factory=dict)
    rosters: dict = field(default_factory=dict)
    sessions: dict = field(default_factory=dict)
    records: dict = field(default_factory=dict)
    changes: list = field(default_factory=list)
    corrections: dict = field(default_factory=dict)


class FakeStore:
    def __init__(self):
        self.lock = RLock()
        self.data = Data()
        self.commits = 0
        self.rollbacks = 0

    @contextmanager
    def unit_of_work(self, actor_id: UUID):
        with self.lock:
            snapshot = copy.deepcopy(self.data)
            try:
                yield FakeUow(self.data, actor_id)
            except BaseException:
                self.data.__dict__.update(snapshot.__dict__)
                self.rollbacks += 1
                raise
            self.commits += 1


class FakeUow:
    def __init__(self, data: Data, actor_id: UUID):
        self.d = data
        self.actor_id = actor_id

    @staticmethod
    def _cas(table: dict, row, expected: int) -> None:
        stored = table.get(row.id)
        if stored is None or stored.revision != expected or row.revision != expected + 1:
            raise ApiError(ErrorCode.CONFLICT)
        table[row.id] = row

    def _claim(self, claim) -> None:
        if claim.actor_id != self.actor_id or claim.namespace in self.d.claims:
            raise ApiError(ErrorCode.CONFLICT)
        self.d.claims[claim.namespace] = claim

    def find_claim(self, namespace):
        return self.d.claims.get(namespace)

    def standing(self):
        return self.d.standings.get(self.actor_id)

    def term_exists(self, term_id):
        return term_id in self.d.terms

    def department_exists(self, department_id):
        return department_id in self.d.departments

    def _count(self, offering_id):
        return sum(
            1
            for e in self.d.enrollments.values()
            if e.offering_id == offering_id and e.status == "ENROLLED"
        )

    def _with_count(self, row: Offering) -> Offering:
        return row.model_copy(update={"enrolled_count": self._count(row.id)})

    def search_offerings(self, term_id, query, limit):
        rows = [
            self._with_count(o)
            for o in self.d.offerings.values()
            if (term_id is None or o.term_id == term_id) and query in o.title
        ]
        return rows[:limit]

    def get_offering(self, offering_id):
        row = self.d.offerings.get(offering_id)
        return self._with_count(row) if row else None

    def lock_seats(self, offering_id):
        row = self.d.offerings.get(offering_id)
        if row is None:
            return None
        return SeatState(capacity=row.capacity, enrolled_count=self._count(offering_id))

    def my_enrollments(self):
        return [e for e in self.d.enrollments.values() if e.student_id == self.actor_id]

    def get_my_enrollment(self, enrollment_id):
        row = self.d.enrollments.get(enrollment_id)
        return row if row and row.student_id == self.actor_id else None

    def insert_enrollment(self, row, claim):
        if row.student_id != self.actor_id or any(
            e.offering_id == row.offering_id and e.status == "ENROLLED"
            for e in self.my_enrollments()
        ):
            raise ApiError(ErrorCode.CONFLICT)
        self._claim(claim)
        self.d.enrollments[row.id] = row

    def update_enrollment(self, row, expected_revision):
        self._cas(self.d.enrollments, row, expected_revision)

    def my_grades(self):
        return [g for g in self.d.grades if g.student_id == self.actor_id]

    def my_requests(self):
        return [r for r in self.d.requests.values() if r.student_id == self.actor_id]

    def get_my_request(self, request_id):
        row = self.d.requests.get(request_id)
        return row if row and row.student_id == self.actor_id else None

    def insert_request(self, row, claim):
        self._claim(claim)
        self.d.requests[row.id] = row

    def update_request(self, row, expected_revision):
        self._cas(self.d.requests, row, expected_revision)

    def attendance_offerings(self, limit):
        return self.d.att_offerings.get(self.actor_id, [])[:limit]

    def attendance_grant(self, offering_id):
        return self.d.grants.get((self.actor_id, offering_id))

    def roster(self, offering_id):
        return list(self.d.rosters.get(offering_id, []))

    def sessions(self, offering_id):
        return [s for s in self.d.sessions.values() if s.offering_id == offering_id]

    def get_session(self, offering_id, session_id):
        row = self.d.sessions.get(session_id)
        return row if row and row.offering_id == offering_id else None

    def insert_session(self, row, claim):
        self._claim(claim)
        self.d.sessions[row.id] = row

    def update_session(self, row, expected_revision):
        self._cas(self.d.sessions, row, expected_revision)

    def records(self, session_id):
        return [r for r in self.d.records.values() if r.session_id == session_id]

    def get_record(self, session_id, student_id):
        return next(
            (
                r
                for r in self.d.records.values()
                if r.session_id == session_id and r.student_id == student_id
            ),
            None,
        )

    def get_record_by_id(self, offering_id, record_id):
        row = self.d.records.get(record_id)
        if row is None or self.get_session(offering_id, row.session_id) is None:
            return None
        return row

    def save_record(self, row, expected_revision):
        existing = self.get_record(row.session_id, row.student_id)
        if expected_revision == 0:
            if existing is not None or row.revision != 1:
                raise ApiError(ErrorCode.CONFLICT)
            self.d.records[row.id] = row
        else:
            self._cas(self.d.records, row, expected_revision)

    def append_change(self, change):
        self.d.changes.append(change)

    def changes(self, record_id):
        return [c for c in self.d.changes if c.record_id == record_id]

    def corrections(self, offering_id):
        return [
            c
            for c in self.d.corrections.values()
            if self.get_session(offering_id, c.session_id) is not None
        ]

    def get_correction(self, offering_id, correction_id):
        row = self.d.corrections.get(correction_id)
        if row is None or self.get_session(offering_id, row.session_id) is None:
            return None
        return row

    def insert_correction(self, row, claim):
        self._claim(claim)
        self.d.corrections[row.id] = row

    def update_correction(self, row, expected_revision):
        self._cas(self.d.corrections, row, expected_revision)


STUDENT_REF, OTHER_REF = uuid4(), uuid4()
GRADE_MINE, GRADE_OTHER = uuid4(), uuid4()


def seeded_store() -> FakeStore:
    store = FakeStore()
    d = store.data
    d.terms |= {TERM, OTHER_TERM}
    d.departments.add(DEPT)
    for actor in (STUDENT, OTHER):
        d.standings[actor.user_id] = StudentStanding(
            access_active=True, registration_term_ids=frozenset({TERM})
        )
    d.offerings = {
        OFFERING_A: offering(OFFERING_A, "가상 자료구조", 3, 2, [slot(1, 540, 630)]),
        OFFERING_B: offering(OFFERING_B, "가상 웹개발", 3, 30, [slot(2, 540, 630)]),
        OFFERING_CLASH: offering(OFFERING_CLASH, "가상 충돌수업", 1, 30, [slot(1, 600, 660)]),
        OFFERING_FULL: offering(OFFERING_FULL, "가상 마감수업", 1, 0, [slot(5, 0, 60)]),
    }
    d.grades = [
        GradeRecord(
            id=gid,
            student_id=owner.user_id,
            offering_id=OFFERING_B,
            term_id=OTHER_TERM,
            course_title="가상 이전 수업",
            credits=3,
            grade_label="DEMO-A",
            recorded_at=NOW - timedelta(days=90),
        )
        for gid, owner in ((GRADE_MINE, STUDENT), (GRADE_OTHER, OTHER))
    ]
    d.rosters[OFFERING_A] = [
        RosterEntry(member_ref=STUDENT_REF, student_id=STUDENT.user_id, label="가상 학생 1"),
        RosterEntry(member_ref=OTHER_REF, student_id=OTHER.user_id, label="가상 학생 2"),
    ]
    for actor, role in ((STUDENT, "student"), (OTHER, "student"), (TEACHER, "teacher")):
        d.grants[(actor.user_id, OFFERING_A)] = AttendanceGrant(active=True, role=role)
        d.att_offerings[actor.user_id] = [
            AttendanceOffering(offering_id=OFFERING_A, title="가상 자료구조", role=role)
        ]
    return store


def make_service(store: FakeStore, policy="default", now=NOW) -> AcademicsService:
    return AcademicsService(
        store,
        demo_policy() if policy == "default" else policy,
        clock=lambda: now,
        code_factory=lambda: CODE,
    )
