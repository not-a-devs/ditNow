from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, Field, model_validator

from app.schemas.common import ApiModel


class LearningActor(ApiModel):
    user_id: UUID


class OfferingRef(ApiModel):
    """References existing course_offerings/academic_terms; never a second enrollment ledger."""
    id: UUID
    term_id: UUID
    title: str = Field(min_length=1,max_length=160)
    section: str = Field(min_length=1,max_length=40)
    source_kind: Literal["DEMO"] = "DEMO"


class EnrollmentGrant(ApiModel):
    active: bool
    current_student: bool
    offering_id: UUID
    term_id: UUID


class DemoLearningPolicy(ApiModel):
    offering_id: UUID
    term_id: UUID
    revision: int = Field(ge=1)
    completion_steps: int = Field(ge=1,le=20)
    max_attempts: int = Field(ge=1,le=10)
    require_all_answers: bool
    source_kind: Literal["DEMO"] = "DEMO"


class LearningStep(ApiModel):
    id: UUID
    text: str = Field(min_length=1,max_length=2000)


class Unit(ApiModel):
    id: UUID
    offering_id: UUID
    title: str = Field(min_length=1,max_length=160)
    steps: list[LearningStep] = Field(min_length=1,max_length=20)
    revision: int = Field(ge=1)
    status: Literal["draft","published","closed"]
    opens_at: AwareDatetime
    closes_at: AwareDatetime
    source_kind: Literal["DEMO"] = "DEMO"

    @model_validator(mode="after")
    def valid_unit(self):
        if self.closes_at<=self.opens_at or len({s.id for s in self.steps})!=len(self.steps):
            raise ValueError("Invalid unit interval or steps")
        return self


class ProgressRecord(ApiModel):
    owner_id: UUID
    offering_id: UUID
    unit_id: UUID
    unit_revision: int = Field(ge=1)
    policy_revision: int = Field(ge=1)
    completed_steps: frozenset[UUID]
    revision: int = Field(ge=1)
    updated_at: AwareDatetime


class ProgressView(ApiModel):
    unit_id: UUID
    completed_steps: list[UUID]
    revision: int = Field(ge=0)
    state: Literal["IN_PROGRESS","DEMO_COMPLETED","STALE_DEMO"]
    evidence: Literal["SELF_REPORTED_DEMO"] = "SELF_REPORTED_DEMO"
    official_attendance: Literal["BLOCKED"] = "BLOCKED"
    source_kind: Literal["DEMO"] = "DEMO"


class ProgressInput(ApiModel):
    step_id: UUID
    expected_revision: int = Field(ge=0)
    expected_unit_revision: int = Field(ge=1)
    expected_policy_revision: int = Field(ge=1)


class Option(ApiModel):
    id: UUID
    text: str = Field(min_length=1,max_length=400)


class QuestionView(ApiModel):
    id: UUID
    prompt: str = Field(min_length=1,max_length=1000)
    options: list[Option] = Field(min_length=2,max_length=8)


class QuestionRecord(QuestionView):
    correct_option_id: UUID = Field(repr=False)

    @model_validator(mode="after")
    def valid_options(self):
        ids={o.id for o in self.options}
        if len(ids)!=len(self.options) or self.correct_option_id not in ids:
            raise ValueError("Invalid private question configuration")
        return self


class ExamRecord(ApiModel):
    id: UUID
    offering_id: UUID
    title: str = Field(min_length=1,max_length=160)
    revision: int = Field(ge=1)
    status: Literal["draft","published","closed"]
    opens_at: AwareDatetime
    closes_at: AwareDatetime
    questions: list[QuestionRecord] = Field(min_length=1,max_length=20,repr=False)
    private_rubric: str = Field(default="",max_length=1000,repr=False)

    @model_validator(mode="after")
    def valid_exam(self):
        if self.closes_at<=self.opens_at or len({q.id for q in self.questions})!=len(self.questions):
            raise ValueError("Invalid exam interval or question IDs")
        return self


class ExamSummary(ApiModel):
    id: UUID
    title: str
    revision: int
    opens_at: AwareDatetime
    closes_at: AwareDatetime
    open_for_demo: bool
    source_kind: Literal["DEMO"] = "DEMO"


class ExamView(ExamSummary):
    questions: list[QuestionView]


class Answer(ApiModel):
    question_id: UUID
    option_id: UUID


class AttemptRecord(ApiModel):
    id: UUID
    owner_id: UUID
    offering_id: UUID
    exam_id: UUID
    exam_revision: int
    policy_revision: int
    state: Literal["in_progress","submitted"]
    answers: list[Answer] = Field(default_factory=list,max_length=20)
    revision: int = Field(ge=1)
    started_at: AwareDatetime
    submitted_at: AwareDatetime | None = None


class AttemptView(ApiModel):
    id: UUID
    exam_id: UUID
    exam_revision: int
    state: Literal["in_progress","submitted"]
    revision: int
    started_at: AwareDatetime
    submitted_at: AwareDatetime | None
    source_kind: Literal["DEMO"] = "DEMO"
    evaluation: Literal["NOT_GRADED"] = "NOT_GRADED"
    official_grade: Literal["BLOCKED"] = "BLOCKED"


class StartInput(ApiModel):
    expected_exam_revision: int = Field(ge=1)
    expected_policy_revision: int = Field(ge=1)


class SubmitInput(StartInput):
    expected_revision: int = Field(ge=1)
    answers: list[Answer] = Field(max_length=20)

    @model_validator(mode="after")
    def unique_answers(self):
        if len({a.question_id for a in self.answers})!=len(self.answers):
            raise ValueError("One selection per question")
        return self


class Workspace(ApiModel):
    offering: OfferingRef
    policy: DemoLearningPolicy
    units: list[Unit] = Field(max_length=50)
    progress: list[ProgressView] = Field(max_length=50)
    exams: list[ExamSummary] = Field(max_length=30)
    attempts: list[AttemptView] = Field(max_length=100)
    source_kind: Literal["DEMO"] = "DEMO"
