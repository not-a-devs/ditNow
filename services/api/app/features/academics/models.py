from datetime import UTC, datetime
from typing import Annotated, Literal, Self
from urllib.parse import urlsplit
from uuid import UUID

from pydantic import AfterValidator, AwareDatetime, Field, model_validator

from app.schemas.common import ApiModel

SourceKind = Literal["DEMO", "OFFICIAL_PUBLIC", "UNKNOWN"]
RequestKind = Literal[
    "LEAVE_OF_ABSENCE", "RETURN_FROM_LEAVE", "READMISSION", "MAJOR_TRANSFER", "GRADE_CORRECTION"
]
RequestStatus = Literal["DRAFT", "SUBMITTED", "WITHDRAWN"]
FinalMark = Literal["PRESENT", "LATE", "ABSENT"]
AttendanceMark = Literal["UNMARKED", "CHECKED_IN", "PRESENT", "LATE", "ABSENT"]

TERM_KINDS: frozenset[str] = frozenset({"LEAVE_OF_ABSENCE", "RETURN_FROM_LEAVE", "READMISSION"})


def utc(value: datetime) -> datetime:
    return value.astimezone(UTC)


def safe_public_url(value: str) -> str:
    parsed = urlsplit(value)
    if (
        len(value) > 2048
        or parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
        or not value.isascii()
        or any(character.isspace() for character in value)
    ):
        raise ValueError("Only a public HTTPS source URL without credentials is allowed")
    try:
        _ = parsed.port
    except ValueError:
        raise ValueError("Invalid source port") from None
    return value


def trimmed(value: str) -> str:
    if not value.strip():
        raise ValueError("Text must not be blank")
    return value.strip()


Trimmed = Annotated[str, AfterValidator(trimmed)]


class AcademicActor(ApiModel):
    """Only an approved authentication bridge may construct a trusted actor."""

    user_id: UUID


class Provenance(ApiModel):
    """OFFICIAL_PUBLIC needs a cited URL and check time; DEMO/UNKNOWN never carry a link."""

    source_kind: SourceKind
    source_url: str | None = None
    checked_at: AwareDatetime | None = None

    @model_validator(mode="after")
    def cited(self) -> Self:
        if self.source_kind == "OFFICIAL_PUBLIC":
            if self.source_url is None or self.checked_at is None:
                raise ValueError("Official public source requires URL and checked_at")
            safe_public_url(self.source_url)
            self.checked_at = utc(self.checked_at)
        elif self.source_url is not None or self.checked_at is not None:
            raise ValueError("Only cited official public sources may carry a link")
        return self


class MeetingSlot(ApiModel):
    weekday: int = Field(ge=1, le=7)
    starts_minute: int = Field(ge=0, le=1439)
    ends_minute: int = Field(ge=1, le=1440)

    @model_validator(mode="after")
    def ordered(self) -> Self:
        if self.ends_minute <= self.starts_minute:
            raise ValueError("Meeting must end after it starts")
        return self

    def overlaps(self, other: "MeetingSlot") -> bool:
        return (
            self.weekday == other.weekday
            and self.starts_minute < other.ends_minute
            and other.starts_minute < self.ends_minute
        )


class Offering(ApiModel):
    """A catalog view keyed by the existing classroom offering ID and campus term ID."""

    id: UUID
    term_id: UUID
    course_code: str = Field(min_length=1, max_length=30)
    title: str = Field(min_length=1, max_length=160)
    section: str = Field(min_length=1, max_length=40)
    instructor_name: str = Field(min_length=1, max_length=80)
    credits: int = Field(ge=0, le=30)
    capacity: int = Field(ge=0, le=10000)
    enrolled_count: int = Field(ge=0)
    meetings: list[MeetingSlot] = Field(max_length=14)
    syllabus_summary: str = Field(max_length=4000)
    syllabus_source: Provenance
    record_source: Literal["DEMO"] = "DEMO"


class SeatState(ApiModel):
    capacity: int = Field(ge=0)
    enrolled_count: int = Field(ge=0)


class StudentStanding(ApiModel):
    """Current eligibility from the approved common ledger, re-read in each unit of work."""

    access_active: bool
    registration_term_ids: frozenset[UUID] = frozenset()


class EnrollInput(ApiModel):
    offering_id: UUID


class RevisionInput(ApiModel):
    expected_revision: int = Field(ge=1)


class EnrollmentRecord(ApiModel):
    id: UUID
    student_id: UUID
    offering_id: UUID
    term_id: UUID
    status: Literal["ENROLLED", "DROPPED"]
    enrolled_at: AwareDatetime
    dropped_at: AwareDatetime | None = None
    revision: int = Field(ge=1)


class EnrollmentView(ApiModel):
    id: UUID
    offering_id: UUID
    term_id: UUID
    status: Literal["ENROLLED", "DROPPED"]
    enrolled_at: AwareDatetime
    dropped_at: AwareDatetime | None
    revision: int
    record_source: Literal["DEMO"] = "DEMO"


class GradeRecord(ApiModel):
    id: UUID
    student_id: UUID
    offering_id: UUID
    term_id: UUID
    course_title: str = Field(min_length=1, max_length=160)
    credits: int = Field(ge=0, le=30)
    grade_label: str = Field(min_length=1, max_length=10)
    recorded_at: AwareDatetime


class GradeView(ApiModel):
    id: UUID
    offering_id: UUID
    term_id: UUID
    course_title: str
    credits: int
    grade_label: str
    recorded_at: AwareDatetime
    record_source: Literal["DEMO"] = "DEMO"


class TranscriptView(ApiModel):
    grades: list[GradeView]
    listed_credit_total: int
    graduation_judgement: Literal["NOT_PROVIDED"] = "NOT_PROVIDED"
    official_effect: Literal["NONE"] = "NONE"
    record_source: Literal["DEMO"] = "DEMO"


class RequestTargets(ApiModel):
    target_term_id: UUID | None = None
    target_department_id: UUID | None = None
    target_grade_id: UUID | None = None
    reason: Trimmed = Field(min_length=1, max_length=2000)


class RequestInput(RequestTargets):
    kind: RequestKind

    @model_validator(mode="after")
    def matching_targets(self) -> Self:
        check_targets(self.kind, self)
        return self


class RequestUpdate(RequestTargets):
    expected_revision: int = Field(ge=1)


def check_targets(kind: str, targets: RequestTargets) -> None:
    term = kind in TERM_KINDS
    department = kind == "MAJOR_TRANSFER"
    grade = kind == "GRADE_CORRECTION"
    if (
        (targets.target_term_id is not None) != term
        or (targets.target_department_id is not None) != department
        or (targets.target_grade_id is not None) != grade
    ):
        raise ValueError("Targets do not match the request kind")


class AcademicRequestRecord(ApiModel):
    id: UUID
    student_id: UUID
    kind: RequestKind
    status: RequestStatus
    target_term_id: UUID | None
    target_department_id: UUID | None
    target_grade_id: UUID | None
    reason: str | None
    created_at: AwareDatetime
    updated_at: AwareDatetime
    submitted_at: AwareDatetime | None = None
    withdrawn_at: AwareDatetime | None = None
    revision: int = Field(ge=1)


class AcademicRequestView(ApiModel):
    id: UUID
    kind: RequestKind
    status: RequestStatus
    target_term_id: UUID | None
    target_department_id: UUID | None
    target_grade_id: UUID | None
    reason: str | None
    created_at: AwareDatetime
    updated_at: AwareDatetime
    submitted_at: AwareDatetime | None
    withdrawn_at: AwareDatetime | None
    revision: int
    review_state: Literal["NOT_CONNECTED"] = "NOT_CONNECTED"
    official_effect: Literal["NONE"] = "NONE"
    record_source: Literal["DEMO"] = "DEMO"


class AttendanceGrant(ApiModel):
    active: bool
    role: Literal["student", "teacher"]


class AttendanceOffering(ApiModel):
    offering_id: UUID
    title: str = Field(min_length=1, max_length=160)
    role: Literal["student", "teacher"]
    record_source: Literal["DEMO"] = "DEMO"


class RosterEntry(ApiModel):
    member_ref: UUID
    student_id: UUID
    label: str = Field(min_length=1, max_length=80)


class SessionInput(ApiModel):
    label: Trimmed = Field(min_length=1, max_length=80)


class SessionRecord(ApiModel):
    id: UUID
    offering_id: UUID
    label: str
    status: Literal["OPEN", "CLOSED"]
    check_in_code: str = Field(pattern=r"^[0-9]{6}$")
    opened_at: AwareDatetime
    check_in_closes_at: AwareDatetime
    closed_at: AwareDatetime | None = None
    revision: int = Field(ge=1)


class SessionView(ApiModel):
    id: UUID
    offering_id: UUID
    label: str
    status: Literal["OPEN", "CLOSED"]
    opened_at: AwareDatetime
    check_in_closes_at: AwareDatetime
    closed_at: AwareDatetime | None
    revision: int
    check_in_code: str | None
    record_source: Literal["DEMO"] = "DEMO"


class CheckInInput(ApiModel):
    method: Literal["DEMO_CODE"]
    code: str = Field(pattern=r"^[0-9]{6}$")


class MarkInput(ApiModel):
    mark: FinalMark
    reason: Trimmed = Field(min_length=1, max_length=500)
    expected_revision: int = Field(ge=0)


class AttendanceRecord(ApiModel):
    id: UUID
    session_id: UUID
    student_id: UUID
    mark: AttendanceMark
    checked_in_at: AwareDatetime | None = None
    failed_attempts: int = Field(default=0, ge=0)
    updated_at: AwareDatetime
    revision: int = Field(ge=1)


class AttendanceRecordView(ApiModel):
    """``id`` is None and ``revision`` 0 while a roster member has no stored record yet."""

    id: UUID | None
    session_id: UUID
    member_ref: UUID | None
    student_label: str | None
    mark: AttendanceMark
    checked_in_at: AwareDatetime | None
    updated_at: AwareDatetime | None
    revision: int = Field(ge=0)
    is_mine: bool
    judgement: Literal["DEMO_DISPLAY_ONLY"] = "DEMO_DISPLAY_ONLY"


class AttendanceChange(ApiModel):
    id: UUID
    record_id: UUID
    actor_id: UUID
    from_mark: AttendanceMark
    to_mark: AttendanceMark
    reason: str
    changed_at: AwareDatetime


class AttendanceChangeView(ApiModel):
    id: UUID
    from_mark: AttendanceMark
    to_mark: AttendanceMark
    reason: str
    changed_at: AwareDatetime
    changed_by_role: Literal["teacher"] = "teacher"


class CorrectionInput(ApiModel):
    requested_mark: FinalMark
    reason: Trimmed = Field(min_length=1, max_length=1000)


class CorrectionRecord(ApiModel):
    id: UUID
    record_id: UUID
    session_id: UUID
    student_id: UUID
    requested_mark: FinalMark
    reason: str
    status: Literal["REQUESTED", "ACCEPTED", "REJECTED"]
    created_at: AwareDatetime
    resolved_at: AwareDatetime | None = None
    revision: int = Field(ge=1)


class CorrectionView(ApiModel):
    id: UUID
    record_id: UUID
    session_id: UUID
    requested_mark: FinalMark
    reason: str
    status: Literal["REQUESTED", "ACCEPTED", "REJECTED"]
    created_at: AwareDatetime
    resolved_at: AwareDatetime | None
    revision: int
    is_mine: bool
    student_label: str | None


class CorrectionResolve(ApiModel):
    decision: Literal["ACCEPTED", "REJECTED"]
    reason: Trimmed = Field(min_length=1, max_length=500)
    expected_revision: int = Field(ge=1)


class MyAttendance(ApiModel):
    sessions: list[SessionView]
    records: list[AttendanceRecordView]
    corrections: list[CorrectionView]
    record_source: Literal["DEMO"] = "DEMO"


class WindowView(ApiModel):
    opens_at: AwareDatetime
    closes_at: AwareDatetime


class PolicyView(ApiModel):
    policy_id: str
    label: str
    registration_windows: dict[str, WindowView]
    request_windows: dict[str, WindowView]
    max_credits_per_term: int
    check_in_window_minutes: int
    check_in_attempt_limit: int
    policy_source: Literal["DEMO"] = "DEMO"
    school_rules: Literal["NOT_CONNECTED"] = "NOT_CONNECTED"
    blocked: list[str]
