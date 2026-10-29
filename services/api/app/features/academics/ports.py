"""Repository/unit-of-work Protocols. No runtime implementation is installed by this feature.

Contract for an approved adapter (atomicity is guaranteed by the adapter's real transaction, NOT
by this module; unit tests only exercise a serialized in-memory fake):

* ``AcademicsStore.unit_of_work(actor_id)`` opens one transaction bound to the trusted actor.
  Commit happens only when the context exits without an exception; any exception rolls back
  every write in that unit, including idempotency claims and change logs.
* ``standing()``/``attendance_grant()`` must be read from the current common ledger inside the
  same transaction as the write (no token claim cache), so revocation applies immediately.
* Term/offering/department IDs are references to the existing campus term and classroom
  offering ledgers; this feature never creates a second term or section authority.
* ``lock_seats`` must lock the offering seat row (e.g. ``SELECT ... FOR UPDATE``) until commit
  so concurrent registrations cannot exceed capacity. Enrollment uniqueness is
  ``(student_id, offering_id)`` among ENROLLED rows.
* ``update_*`` methods are CAS writes: they must raise ``ApiError(CONFLICT)`` when the stored
  revision differs from ``expected_revision`` and must store ``row.revision`` (= expected + 1).

Aggregate locks (TASK-M review fix). Each ``lock_*`` takes an exclusive row lock that is held
until commit/rollback, so a second transaction on the same aggregate blocks instead of deciding
from the same stale state. The service always calls them in one global order, which prevents
lock-order deadlocks between its own flows:

  registration(actor, term) -> seat(offering)
  student requests(actor)
  offering sessions(offering) -> session(row) -> attendance record(row) -> correction(row)

* ``lock_registration(term_id)`` locks the bound actor's registration aggregate for one term
  (e.g. a ``(student_id, term_id)`` row read ``FOR UPDATE``). ``enroll`` and ``drop`` take it
  before reading the active list, credit total and time conflicts, then take ``lock_seats``.
  Two enrollments of the same student in *different* offerings therefore serialize; the seat
  lock alone does not.
* ``lock_requests()`` locks the bound actor's virtual-request aggregate. ``create/update/
  submit/withdraw_request`` take it before the active-duplicate check. The duplicate key is the
  existing policy key (kind, target_grade_id) among DRAFT/SUBMITTED; a unique index cannot
  express it alone because MariaDB unique indexes accept repeated NULLs, so the lock is the
  primary guard.
* ``lock_offering_sessions(offering_id)`` locks the offering's attendance aggregate. ``open``
  and ``close_session`` take it, so two teachers of the same offering cannot both open a
  session. An adapter should additionally enforce "at most one OPEN session per offering"
  (e.g. a unique index on a nullable generated ``open_offering_id``) as defense in depth.
* ``lock_session(offering_id, session_id)`` is a locking read of the session row.
  ``close_session`` (after the offering lock) and ``check_in`` take it, so a check-in either
  commits before the close or reads the CLOSED state; per-session check-ins are serialized,
  which also orders each student's failed-attempt counter increments. The record write itself
  stays a CAS (``save_record``; first insert relies on unique ``(session_id, student_id)``), so
  a concurrent teacher ``mark`` on the same record loses with CONFLICT rather than overwriting.
* ``lock_record(offering_id, record_id)`` is a locking read of the attendance record row.
  ``request_correction`` and ``resolve_correction`` take it before reading corrections, so one
  record has at most one REQUESTED correction.

Read consistency after a lock (an adapter contract, not a decided infrastructure policy):
under MariaDB/InnoDB REPEATABLE READ the snapshot is fixed by the transaction's first
consistent read, and a plain ``SELECT`` after acquiring a lock can still return that older
snapshot. Every read that a decision depends on after a ``lock_*`` call (``standing``,
``attendance_grant``, ``find_claim``, ``my_enrollments``, ``my_requests``, ``sessions``,
``get_*``, ``corrections``, seat counts) must therefore be a current read: either run the unit
at READ COMMITTED, or issue those reads as locking reads (``FOR UPDATE`` /
``LOCK IN SHARE MODE``) so they see the latest committed rows. The service re-checks
standing/grants after locking for this reason. Sources (checked 2026-10-30):
https://mariadb.com/docs/server/reference/sql-statements/transactions/transactions-repeatable-read
https://mariadb.com/docs/server/reference/sql-statements/data-manipulation/selecting-data/for-update
The isolation level and lock-row schema are not chosen yet; no real MariaDB run has verified
this contract.
* ``insert_*`` methods persist the row and its ``IdempotencyClaim`` atomically; the claim
  namespace is unique. Dropped/withdrawn rows and their claims are retained as tombstones.
* Every ``my_*``/``get_*`` read is scoped to the bound actor (or the given offering for a
  teacher) and returns None/empty for anything else; callers turn that into 404.
"""

from contextlib import AbstractContextManager
from typing import Protocol
from uuid import UUID

from app.features.academics.idempotency import IdempotencyClaim
from app.features.academics.models import (
    AcademicRequestRecord,
    AttendanceChange,
    AttendanceGrant,
    AttendanceOffering,
    AttendanceRecord,
    CorrectionRecord,
    EnrollmentRecord,
    GradeRecord,
    Offering,
    RosterEntry,
    SeatState,
    SessionRecord,
    StudentStanding,
)


class AcademicsUnitOfWork(Protocol):
    actor_id: UUID

    def find_claim(self, namespace: tuple[UUID, str, str, str]) -> IdempotencyClaim | None: ...

    # Common ledger references (read-only here)
    def standing(self) -> StudentStanding | None: ...

    def term_exists(self, term_id: UUID) -> bool: ...

    def department_exists(self, department_id: UUID) -> bool: ...

    # FR-ACA-003 catalog
    def search_offerings(self, term_id: UUID | None, query: str, limit: int) -> list[Offering]: ...

    def get_offering(self, offering_id: UUID) -> Offering | None: ...

    # Aggregate locks: held until the unit ends; see module docstring for order and reads.
    def lock_registration(self, term_id: UUID) -> None: ...

    def lock_requests(self) -> None: ...

    def lock_offering_sessions(self, offering_id: UUID) -> None: ...

    def lock_session(self, offering_id: UUID, session_id: UUID) -> SessionRecord | None: ...

    def lock_record(self, offering_id: UUID, record_id: UUID) -> AttendanceRecord | None: ...

    # FR-ACA-004 registration
    def lock_seats(self, offering_id: UUID) -> SeatState | None: ...

    def my_enrollments(self) -> list[EnrollmentRecord]: ...

    def get_my_enrollment(self, enrollment_id: UUID) -> EnrollmentRecord | None: ...

    def insert_enrollment(self, row: EnrollmentRecord, claim: IdempotencyClaim) -> None: ...

    def update_enrollment(self, row: EnrollmentRecord, expected_revision: int) -> None: ...

    # FR-ACA-005 demo grades
    def my_grades(self) -> list[GradeRecord]: ...

    # FR-ACA-006~009 virtual requests
    def my_requests(self) -> list[AcademicRequestRecord]: ...

    def get_my_request(self, request_id: UUID) -> AcademicRequestRecord | None: ...

    def insert_request(self, row: AcademicRequestRecord, claim: IdempotencyClaim) -> None: ...

    def update_request(self, row: AcademicRequestRecord, expected_revision: int) -> None: ...

    # FR-ATT-001~002 demo attendance
    def attendance_offerings(self, limit: int) -> list[AttendanceOffering]: ...

    def attendance_grant(self, offering_id: UUID) -> AttendanceGrant | None: ...

    def roster(self, offering_id: UUID) -> list[RosterEntry]: ...

    def sessions(self, offering_id: UUID) -> list[SessionRecord]: ...

    def get_session(self, offering_id: UUID, session_id: UUID) -> SessionRecord | None: ...

    def insert_session(self, row: SessionRecord, claim: IdempotencyClaim) -> None: ...

    def update_session(self, row: SessionRecord, expected_revision: int) -> None: ...

    def records(self, session_id: UUID) -> list[AttendanceRecord]: ...

    def get_record(self, session_id: UUID, student_id: UUID) -> AttendanceRecord | None: ...

    def get_record_by_id(self, offering_id: UUID, record_id: UUID) -> AttendanceRecord | None: ...

    def save_record(self, row: AttendanceRecord, expected_revision: int) -> None:
        """CAS upsert; expected_revision 0 means the record must not exist yet."""
        ...

    def append_change(self, change: AttendanceChange) -> None: ...

    def changes(self, record_id: UUID) -> list[AttendanceChange]: ...

    def corrections(self, offering_id: UUID) -> list[CorrectionRecord]: ...

    def get_correction(self, offering_id: UUID, correction_id: UUID) -> CorrectionRecord | None: ...

    def insert_correction(self, row: CorrectionRecord, claim: IdempotencyClaim) -> None: ...

    def update_correction(self, row: CorrectionRecord, expected_revision: int) -> None: ...


class AcademicsStore(Protocol):
    def unit_of_work(self, actor_id: UUID) -> AbstractContextManager[AcademicsUnitOfWork]: ...
