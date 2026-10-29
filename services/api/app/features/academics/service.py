import hmac
import secrets
from collections.abc import Callable
from datetime import UTC, datetime
from uuid import UUID, uuid4

from app.core.errors import ApiError
from app.features.academics.idempotency import claim_for, replayed_resource
from app.features.academics.models import (
    AcademicActor,
    AcademicRequestRecord,
    AcademicRequestView,
    AttendanceChange,
    AttendanceChangeView,
    AttendanceGrant,
    AttendanceOffering,
    AttendanceRecord,
    AttendanceRecordView,
    CheckInInput,
    CorrectionInput,
    CorrectionRecord,
    CorrectionResolve,
    CorrectionView,
    EnrollInput,
    EnrollmentRecord,
    EnrollmentView,
    GradeView,
    MarkInput,
    MyAttendance,
    Offering,
    PolicyView,
    RequestInput,
    RequestUpdate,
    RevisionInput,
    RosterEntry,
    SessionInput,
    SessionRecord,
    SessionView,
    StudentStanding,
    TranscriptView,
    check_targets,
)
from app.features.academics.policy import DemoAcademicPolicy
from app.features.academics.ports import AcademicsStore, AcademicsUnitOfWork
from app.schemas.common import ErrorCode

ACTIVE_REQUEST = frozenset({"DRAFT", "SUBMITTED"})
FINAL_MARKS = frozenset({"PRESENT", "LATE", "ABSENT"})


class AcademicsError(ApiError):
    """ApiError with a fixed, non-sensitive rule code that the router exposes to the client."""

    def __init__(self, code: ErrorCode, rule: str):
        super().__init__(code)
        self.rule = rule


def conflict(rule: str) -> AcademicsError:
    return AcademicsError(ErrorCode.CONFLICT, rule)


def utc_now() -> datetime:
    return datetime.now(UTC)


def demo_code() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def _enrollment_view(row: EnrollmentRecord) -> EnrollmentView:
    return EnrollmentView(**row.model_dump(exclude={"student_id"}))


def _request_view(row: AcademicRequestRecord) -> AcademicRequestView:
    return AcademicRequestView(**row.model_dump(exclude={"student_id"}))


def _session_view(row: SessionRecord, teacher: bool) -> SessionView:
    return SessionView(
        **row.model_dump(exclude={"check_in_code"}),
        check_in_code=row.check_in_code if teacher else None,
    )


class AcademicsService:
    def __init__(
        self,
        store: AcademicsStore,
        policy: DemoAcademicPolicy | None,
        clock: Callable[[], datetime] = utc_now,
        code_factory: Callable[[], str] = demo_code,
    ):
        self.store = store
        self.policy = policy
        self.clock = clock
        self.code_factory = code_factory

    # -- shared guards -------------------------------------------------------------------------

    def _now(self) -> datetime:
        now = self.clock()
        if now.tzinfo is None or now.utcoffset() is None:
            raise ApiError(ErrorCode.UNAVAILABLE)
        return now.astimezone(UTC)

    def _policy(self) -> DemoAcademicPolicy:
        if self.policy is None:
            raise ApiError(ErrorCode.UNAVAILABLE)
        return self.policy

    @staticmethod
    def _student(uow: AcademicsUnitOfWork) -> StudentStanding:
        standing = uow.standing()
        if standing is None or not standing.access_active:
            raise ApiError(ErrorCode.FORBIDDEN)
        return standing

    @staticmethod
    def _grant(
        uow: AcademicsUnitOfWork, offering_id: UUID, role: str | None = None
    ) -> AttendanceGrant:
        grant = uow.attendance_grant(offering_id)
        if grant is None:
            raise ApiError(ErrorCode.NOT_FOUND)
        if not grant.active or (role is not None and grant.role != role):
            raise ApiError(ErrorCode.FORBIDDEN)
        return grant

    @staticmethod
    def _cas(revision: int, expected: int) -> None:
        if revision != expected:
            raise conflict("STALE_REVISION")

    def policy_view(self, actor: AcademicActor) -> PolicyView:
        return self._policy().view()

    # -- FR-ACA-003 catalog --------------------------------------------------------------------

    def search_offerings(
        self, actor: AcademicActor, term_id: UUID | None, query: str, limit: int
    ) -> list[Offering]:
        with self.store.unit_of_work(actor.user_id) as uow:
            return uow.search_offerings(term_id, query.strip(), limit)[:limit]

    def get_offering(self, actor: AcademicActor, offering_id: UUID) -> Offering:
        with self.store.unit_of_work(actor.user_id) as uow:
            offering = uow.get_offering(offering_id)
            if offering is None:
                raise ApiError(ErrorCode.NOT_FOUND)
            return offering

    # -- FR-ACA-004 registration ---------------------------------------------------------------

    def my_enrollments(self, actor: AcademicActor) -> list[EnrollmentView]:
        with self.store.unit_of_work(actor.user_id) as uow:
            self._student(uow)
            return [_enrollment_view(row) for row in uow.my_enrollments()]

    def enroll(self, actor: AcademicActor, body: EnrollInput, key: str) -> EnrollmentView:
        policy = self._policy()
        with self.store.unit_of_work(actor.user_id) as uow:
            standing = self._student(uow)
            claim = claim_for(
                actor.user_id, "/academics/enrollments", key, body.model_dump(mode="json"), uuid4()
            )
            replay = replayed_resource(uow.find_claim(claim.namespace), claim)
            if replay is not None:
                return _enrollment_view(self._replayed(uow.get_my_enrollment(replay)))
            offering = uow.get_offering(body.offering_id)
            if offering is None:
                raise ApiError(ErrorCode.NOT_FOUND)
            if offering.term_id not in standing.registration_term_ids:
                raise ApiError(ErrorCode.FORBIDDEN)
            window = policy.registration_windows.get(offering.term_id)
            if window is None:
                raise ApiError(ErrorCode.UNAVAILABLE)
            now = self._now()
            if not window.contains(now):
                raise conflict("WINDOW_CLOSED")
            active = [row for row in uow.my_enrollments() if row.status == "ENROLLED"]
            if any(row.offering_id == offering.id for row in active):
                raise conflict("ALREADY_ENROLLED")
            credits = offering.credits
            for row in active:
                if row.term_id != offering.term_id:
                    continue
                other = uow.get_offering(row.offering_id)
                if other is None:
                    raise ApiError(ErrorCode.UNAVAILABLE)
                credits += other.credits
                if any(a.overlaps(b) for a in offering.meetings for b in other.meetings):
                    raise conflict("TIME_CONFLICT")
            if credits > policy.max_credits_per_term:
                raise conflict("CREDIT_LIMIT")
            seats = uow.lock_seats(offering.id)
            if seats is None:
                raise ApiError(ErrorCode.NOT_FOUND)
            if seats.enrolled_count >= seats.capacity:
                raise conflict("CAPACITY_FULL")
            row = EnrollmentRecord(
                id=claim.resource_id,
                student_id=actor.user_id,
                offering_id=offering.id,
                term_id=offering.term_id,
                status="ENROLLED",
                enrolled_at=now,
                revision=1,
            )
            uow.insert_enrollment(row, claim)
            return _enrollment_view(row)

    def drop(
        self, actor: AcademicActor, enrollment_id: UUID, body: RevisionInput
    ) -> EnrollmentView:
        policy = self._policy()
        with self.store.unit_of_work(actor.user_id) as uow:
            self._student(uow)
            row = uow.get_my_enrollment(enrollment_id)
            if row is None:
                raise ApiError(ErrorCode.NOT_FOUND)
            if row.status != "ENROLLED":
                raise conflict("INVALID_STATE")
            self._cas(row.revision, body.expected_revision)
            window = policy.registration_windows.get(row.term_id)
            if window is None:
                raise ApiError(ErrorCode.UNAVAILABLE)
            now = self._now()
            if not window.contains(now):
                raise conflict("WINDOW_CLOSED")
            if uow.lock_seats(row.offering_id) is None:
                raise ApiError(ErrorCode.NOT_FOUND)
            dropped = row.model_copy(
                update={"status": "DROPPED", "dropped_at": now, "revision": row.revision + 1}
            )
            uow.update_enrollment(dropped, body.expected_revision)
            return _enrollment_view(dropped)

    @staticmethod
    def _replayed[T](row: T | None) -> T:
        if row is None:
            # Tombstones are retained, so a claim without its row is a broken adapter.
            raise ApiError(ErrorCode.INTERNAL)
        return row

    # -- FR-ACA-005 demo record ----------------------------------------------------------------

    def transcript(self, actor: AcademicActor) -> TranscriptView:
        with self.store.unit_of_work(actor.user_id) as uow:
            self._student(uow)
            grades = [
                GradeView(**row.model_dump(exclude={"student_id"}))
                for row in uow.my_grades()
                if row.student_id == actor.user_id
            ]
            return TranscriptView(
                grades=grades, listed_credit_total=sum(grade.credits for grade in grades)
            )

    # -- FR-ACA-006~009 virtual requests -------------------------------------------------------

    def my_requests(self, actor: AcademicActor) -> list[AcademicRequestView]:
        with self.store.unit_of_work(actor.user_id) as uow:
            self._student(uow)
            rows = sorted(uow.my_requests(), key=lambda row: row.created_at, reverse=True)
            return [_request_view(row) for row in rows]

    @staticmethod
    def _check_references(uow: AcademicsUnitOfWork, actor_id: UUID, body) -> None:
        if body.target_term_id is not None and not uow.term_exists(body.target_term_id):
            raise ApiError(ErrorCode.NOT_FOUND)
        if body.target_department_id is not None and not uow.department_exists(
            body.target_department_id
        ):
            raise ApiError(ErrorCode.NOT_FOUND)
        if body.target_grade_id is not None and not any(
            grade.id == body.target_grade_id and grade.student_id == actor_id
            for grade in uow.my_grades()
        ):
            raise ApiError(ErrorCode.NOT_FOUND)

    @staticmethod
    def _reject_duplicate(
        uow: AcademicsUnitOfWork, kind: str, grade_id: UUID | None, own_id: UUID | None = None
    ) -> None:
        for row in uow.my_requests():
            if (
                row.id != own_id
                and row.status in ACTIVE_REQUEST
                and row.kind == kind
                and row.target_grade_id == grade_id
            ):
                raise conflict("ACTIVE_REQUEST_EXISTS")

    def create_request(
        self, actor: AcademicActor, body: RequestInput, key: str
    ) -> AcademicRequestView:
        policy = self._policy()
        with self.store.unit_of_work(actor.user_id) as uow:
            self._student(uow)
            claim = claim_for(
                actor.user_id, "/academics/requests", key, body.model_dump(mode="json"), uuid4()
            )
            replay = replayed_resource(uow.find_claim(claim.namespace), claim)
            if replay is not None:
                return _request_view(self._replayed(uow.get_my_request(replay)))
            if body.kind not in policy.request_windows:
                raise ApiError(ErrorCode.UNAVAILABLE)
            self._check_references(uow, actor.user_id, body)
            self._reject_duplicate(uow, body.kind, body.target_grade_id)
            now = self._now()
            row = AcademicRequestRecord(
                id=claim.resource_id,
                student_id=actor.user_id,
                status="DRAFT",
                created_at=now,
                updated_at=now,
                revision=1,
                **body.model_dump(),
            )
            uow.insert_request(row, claim)
            return _request_view(row)

    def _own_request(self, uow: AcademicsUnitOfWork, request_id: UUID) -> AcademicRequestRecord:
        row = uow.get_my_request(request_id)
        if row is None:
            raise ApiError(ErrorCode.NOT_FOUND)
        return row

    def update_request(
        self, actor: AcademicActor, request_id: UUID, body: RequestUpdate
    ) -> AcademicRequestView:
        policy = self._policy()
        with self.store.unit_of_work(actor.user_id) as uow:
            self._student(uow)
            row = self._own_request(uow, request_id)
            if row.status != "DRAFT":
                raise conflict("INVALID_STATE")
            self._cas(row.revision, body.expected_revision)
            if row.kind not in policy.request_windows:
                raise ApiError(ErrorCode.UNAVAILABLE)
            try:
                check_targets(row.kind, body)
            except ValueError:
                raise ApiError(ErrorCode.VALIDATION) from None
            self._check_references(uow, actor.user_id, body)
            self._reject_duplicate(uow, row.kind, body.target_grade_id, own_id=row.id)
            changed = row.model_copy(
                update={
                    **body.model_dump(exclude={"expected_revision"}),
                    "updated_at": self._now(),
                    "revision": row.revision + 1,
                }
            )
            uow.update_request(changed, body.expected_revision)
            return _request_view(changed)

    def submit_request(
        self, actor: AcademicActor, request_id: UUID, body: RevisionInput
    ) -> AcademicRequestView:
        policy = self._policy()
        with self.store.unit_of_work(actor.user_id) as uow:
            self._student(uow)
            row = self._own_request(uow, request_id)
            if row.status != "DRAFT":
                raise conflict("INVALID_STATE")
            self._cas(row.revision, body.expected_revision)
            window = policy.request_windows.get(row.kind)
            if window is None:
                raise ApiError(ErrorCode.UNAVAILABLE)
            now = self._now()
            if not window.contains(now):
                raise conflict("WINDOW_CLOSED")
            changed = row.model_copy(
                update={
                    "status": "SUBMITTED",
                    "submitted_at": now,
                    "updated_at": now,
                    "revision": row.revision + 1,
                }
            )
            uow.update_request(changed, body.expected_revision)
            return _request_view(changed)

    def withdraw_request(
        self, actor: AcademicActor, request_id: UUID, body: RevisionInput
    ) -> AcademicRequestView:
        self._policy()
        with self.store.unit_of_work(actor.user_id) as uow:
            self._student(uow)
            row = self._own_request(uow, request_id)
            if row.status not in ACTIVE_REQUEST:
                raise conflict("INVALID_STATE")
            self._cas(row.revision, body.expected_revision)
            now = self._now()
            # Tombstone: identity/state/timestamps stay; the free-text reason is minimized.
            changed = row.model_copy(
                update={
                    "status": "WITHDRAWN",
                    "reason": None,
                    "withdrawn_at": now,
                    "updated_at": now,
                    "revision": row.revision + 1,
                }
            )
            uow.update_request(changed, body.expected_revision)
            return _request_view(changed)

    # -- FR-ATT-001~002 demo attendance --------------------------------------------------------

    def attendance_offerings(self, actor: AcademicActor, limit: int) -> list[AttendanceOffering]:
        with self.store.unit_of_work(actor.user_id) as uow:
            result = []
            for item in uow.attendance_offerings(limit)[:limit]:
                grant = uow.attendance_grant(item.offering_id)
                if grant is not None and grant.active and grant.role == item.role:
                    result.append(item)
            return result

    def sessions(self, actor: AcademicActor, offering_id: UUID) -> list[SessionView]:
        with self.store.unit_of_work(actor.user_id) as uow:
            grant = self._grant(uow, offering_id)
            teacher = grant.role == "teacher"
            return [_session_view(row, teacher) for row in uow.sessions(offering_id)]

    def open_session(
        self, actor: AcademicActor, offering_id: UUID, body: SessionInput, key: str
    ) -> SessionView:
        policy = self._policy()
        with self.store.unit_of_work(actor.user_id) as uow:
            self._grant(uow, offering_id, "teacher")
            claim = claim_for(
                actor.user_id,
                f"/academics/attendance/offerings/{offering_id}/sessions",
                key,
                body.model_dump(mode="json"),
                uuid4(),
            )
            replay = replayed_resource(uow.find_claim(claim.namespace), claim)
            if replay is not None:
                return _session_view(self._replayed(uow.get_session(offering_id, replay)), True)
            if any(row.status == "OPEN" for row in uow.sessions(offering_id)):
                raise conflict("SESSION_ALREADY_OPEN")
            now = self._now()
            row = SessionRecord(
                id=claim.resource_id,
                offering_id=offering_id,
                label=body.label,
                status="OPEN",
                check_in_code=self.code_factory(),
                opened_at=now,
                check_in_closes_at=now + policy.check_in_window,
                revision=1,
            )
            uow.insert_session(row, claim)
            return _session_view(row, True)

    def _session(
        self, uow: AcademicsUnitOfWork, offering_id: UUID, session_id: UUID
    ) -> SessionRecord:
        row = uow.get_session(offering_id, session_id)
        if row is None or row.offering_id != offering_id:
            raise ApiError(ErrorCode.NOT_FOUND)
        return row

    def close_session(
        self, actor: AcademicActor, offering_id: UUID, session_id: UUID, body: RevisionInput
    ) -> SessionView:
        self._policy()
        with self.store.unit_of_work(actor.user_id) as uow:
            self._grant(uow, offering_id, "teacher")
            row = self._session(uow, offering_id, session_id)
            if row.status != "OPEN":
                raise conflict("INVALID_STATE")
            self._cas(row.revision, body.expected_revision)
            closed = row.model_copy(
                update={"status": "CLOSED", "closed_at": self._now(), "revision": row.revision + 1}
            )
            uow.update_session(closed, body.expected_revision)
            return _session_view(closed, True)

    @staticmethod
    def _record_view(
        row: AttendanceRecord, actor_id: UUID, member: RosterEntry | None
    ) -> AttendanceRecordView:
        return AttendanceRecordView(
            id=row.id,
            session_id=row.session_id,
            member_ref=member.member_ref if member else None,
            student_label=member.label if member else None,
            mark=row.mark,
            checked_in_at=row.checked_in_at,
            updated_at=row.updated_at,
            revision=row.revision,
            is_mine=row.student_id == actor_id,
        )

    def check_in(
        self, actor: AcademicActor, offering_id: UUID, session_id: UUID, body: CheckInInput
    ) -> AttendanceRecordView:
        policy = self._policy()
        mismatch = False
        with self.store.unit_of_work(actor.user_id) as uow:
            self._grant(uow, offering_id, "student")
            session = self._session(uow, offering_id, session_id)
            now = self._now()
            if session.status != "OPEN" or now >= session.check_in_closes_at:
                raise conflict("SESSION_CLOSED")
            record = uow.get_record(session_id, actor.user_id)
            if record is not None and record.mark == "CHECKED_IN":
                return self._record_view(record, actor.user_id, None)
            if record is not None and record.mark != "UNMARKED":
                raise conflict("ALREADY_FINAL")
            attempts = record.failed_attempts if record else 0
            if attempts >= policy.check_in_attempt_limit:
                raise AcademicsError(ErrorCode.RATE_LIMITED, "ATTEMPT_LIMIT")
            base = record or AttendanceRecord(
                id=uuid4(),
                session_id=session_id,
                student_id=actor.user_id,
                mark="UNMARKED",
                updated_at=now,
                revision=1,
            )
            expected = record.revision if record else 0
            if hmac.compare_digest(body.code.encode(), session.check_in_code.encode()):
                saved = base.model_copy(
                    update={
                        "mark": "CHECKED_IN",
                        "checked_in_at": now,
                        "updated_at": now,
                        "revision": expected + 1,
                    }
                )
            else:
                # The failed attempt must be committed, so the error is raised after commit.
                mismatch = True
                saved = base.model_copy(
                    update={
                        "failed_attempts": attempts + 1,
                        "updated_at": now,
                        "revision": expected + 1,
                    }
                )
            uow.save_record(saved, expected)
        if mismatch:
            raise AcademicsError(ErrorCode.VALIDATION, "CODE_MISMATCH")
        return self._record_view(saved, actor.user_id, None)

    def session_records(
        self, actor: AcademicActor, offering_id: UUID, session_id: UUID
    ) -> list[AttendanceRecordView]:
        with self.store.unit_of_work(actor.user_id) as uow:
            self._grant(uow, offering_id, "teacher")
            self._session(uow, offering_id, session_id)
            stored = {row.student_id: row for row in uow.records(session_id)}
            result = []
            for member in uow.roster(offering_id):
                row = stored.get(member.student_id)
                if row is None:
                    result.append(
                        AttendanceRecordView(
                            id=None,
                            session_id=session_id,
                            member_ref=member.member_ref,
                            student_label=member.label,
                            mark="UNMARKED",
                            checked_in_at=None,
                            updated_at=None,
                            revision=0,
                            is_mine=False,
                        )
                    )
                else:
                    result.append(self._record_view(row, actor.user_id, member))
            return result

    def mark(
        self,
        actor: AcademicActor,
        offering_id: UUID,
        session_id: UUID,
        member_ref: UUID,
        body: MarkInput,
    ) -> AttendanceRecordView:
        self._policy()
        with self.store.unit_of_work(actor.user_id) as uow:
            self._grant(uow, offering_id, "teacher")
            self._session(uow, offering_id, session_id)
            member = next((m for m in uow.roster(offering_id) if m.member_ref == member_ref), None)
            if member is None:
                raise ApiError(ErrorCode.NOT_FOUND)
            record = uow.get_record(session_id, member.student_id)
            self._cas(record.revision if record else 0, body.expected_revision)
            now = self._now()
            saved = self._apply_mark(
                uow,
                actor.user_id,
                session_id,
                member.student_id,
                record,
                body.mark,
                body.reason,
                now,
            )
            return self._record_view(saved, actor.user_id, member)

    @staticmethod
    def _apply_mark(
        uow: AcademicsUnitOfWork,
        actor_id: UUID,
        session_id: UUID,
        student_id: UUID,
        record: AttendanceRecord | None,
        mark: str,
        reason: str,
        now: datetime,
    ) -> AttendanceRecord:
        expected = record.revision if record else 0
        base = record or AttendanceRecord(
            id=uuid4(),
            session_id=session_id,
            student_id=student_id,
            mark="UNMARKED",
            updated_at=now,
            revision=1,
        )
        saved = base.model_copy(update={"mark": mark, "updated_at": now, "revision": expected + 1})
        uow.save_record(saved, expected)
        uow.append_change(
            AttendanceChange(
                id=uuid4(),
                record_id=saved.id,
                actor_id=actor_id,
                from_mark=base.mark,
                to_mark=saved.mark,
                reason=reason,
                changed_at=now,
            )
        )
        return saved

    def record_history(
        self, actor: AcademicActor, offering_id: UUID, record_id: UUID
    ) -> list[AttendanceChangeView]:
        with self.store.unit_of_work(actor.user_id) as uow:
            self._grant(uow, offering_id, "teacher")
            if uow.get_record_by_id(offering_id, record_id) is None:
                raise ApiError(ErrorCode.NOT_FOUND)
            return [
                AttendanceChangeView(**change.model_dump(exclude={"actor_id", "record_id"}))
                for change in sorted(uow.changes(record_id), key=lambda c: c.changed_at)
            ]

    @staticmethod
    def _correction_view(
        row: CorrectionRecord, actor_id: UUID, labels: dict[UUID, str]
    ) -> CorrectionView:
        return CorrectionView(
            **row.model_dump(exclude={"student_id"}),
            is_mine=row.student_id == actor_id,
            student_label=labels.get(row.student_id),
        )

    def my_attendance(self, actor: AcademicActor, offering_id: UUID) -> MyAttendance:
        with self.store.unit_of_work(actor.user_id) as uow:
            self._grant(uow, offering_id, "student")
            sessions = uow.sessions(offering_id)
            records = [
                self._record_view(record, actor.user_id, None)
                for session in sessions
                if (record := uow.get_record(session.id, actor.user_id)) is not None
                and record.student_id == actor.user_id
            ]
            corrections = [
                self._correction_view(row, actor.user_id, {})
                for row in uow.corrections(offering_id)
                if row.student_id == actor.user_id
            ]
            return MyAttendance(
                sessions=[_session_view(row, False) for row in sessions],
                records=records,
                corrections=corrections,
            )

    def request_correction(
        self,
        actor: AcademicActor,
        offering_id: UUID,
        record_id: UUID,
        body: CorrectionInput,
        key: str,
    ) -> CorrectionView:
        self._policy()
        with self.store.unit_of_work(actor.user_id) as uow:
            self._grant(uow, offering_id, "student")
            claim = claim_for(
                actor.user_id,
                f"/academics/attendance/offerings/{offering_id}/records/{record_id}/corrections",
                key,
                body.model_dump(mode="json"),
                uuid4(),
            )
            replay = replayed_resource(uow.find_claim(claim.namespace), claim)
            if replay is not None:
                row = self._replayed(uow.get_correction(offering_id, replay))
                return self._correction_view(row, actor.user_id, {})
            record = uow.get_record_by_id(offering_id, record_id)
            if record is None or record.student_id != actor.user_id:
                raise ApiError(ErrorCode.NOT_FOUND)
            if record.mark not in FINAL_MARKS:
                raise conflict("INVALID_STATE")
            if any(
                row.record_id == record_id and row.status == "REQUESTED"
                for row in uow.corrections(offering_id)
            ):
                raise conflict("ACTIVE_REQUEST_EXISTS")
            row = CorrectionRecord(
                id=claim.resource_id,
                record_id=record_id,
                session_id=record.session_id,
                student_id=actor.user_id,
                requested_mark=body.requested_mark,
                reason=body.reason,
                status="REQUESTED",
                created_at=self._now(),
                revision=1,
            )
            uow.insert_correction(row, claim)
            return self._correction_view(row, actor.user_id, {})

    def corrections(self, actor: AcademicActor, offering_id: UUID) -> list[CorrectionView]:
        with self.store.unit_of_work(actor.user_id) as uow:
            self._grant(uow, offering_id, "teacher")
            labels = {member.student_id: member.label for member in uow.roster(offering_id)}
            return [
                self._correction_view(row, actor.user_id, labels)
                for row in uow.corrections(offering_id)
            ]

    def resolve_correction(
        self,
        actor: AcademicActor,
        offering_id: UUID,
        correction_id: UUID,
        body: CorrectionResolve,
    ) -> CorrectionView:
        self._policy()
        with self.store.unit_of_work(actor.user_id) as uow:
            self._grant(uow, offering_id, "teacher")
            row = uow.get_correction(offering_id, correction_id)
            if row is None:
                raise ApiError(ErrorCode.NOT_FOUND)
            if row.status != "REQUESTED":
                raise conflict("INVALID_STATE")
            self._cas(row.revision, body.expected_revision)
            now = self._now()
            if body.decision == "ACCEPTED":
                record = uow.get_record_by_id(offering_id, row.record_id)
                if record is None:
                    raise ApiError(ErrorCode.NOT_FOUND)
                self._apply_mark(
                    uow,
                    actor.user_id,
                    record.session_id,
                    record.student_id,
                    record,
                    row.requested_mark,
                    body.reason,
                    now,
                )
            resolved = row.model_copy(
                update={"status": body.decision, "resolved_at": now, "revision": row.revision + 1}
            )
            uow.update_correction(resolved, body.expected_revision)
            labels = {member.student_id: member.label for member in uow.roster(offering_id)}
            return self._correction_view(resolved, actor.user_id, labels)
