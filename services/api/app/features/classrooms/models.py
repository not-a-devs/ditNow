from datetime import UTC, datetime
from typing import Literal
from urllib.parse import urlsplit
from uuid import UUID

from pydantic import AwareDatetime, Field, field_validator

from app.schemas.common import ApiModel


class ClassroomActor(ApiModel):
    """Only an approved authentication bridge may construct a trusted actor."""

    user_id: UUID


class Offering(ApiModel):
    id: UUID
    title: str = Field(min_length=1, max_length=160)
    term: str = Field(min_length=1, max_length=60)
    section: str = Field(min_length=1, max_length=40)
    instructor_name: str = Field(min_length=1, max_length=80)
    source_kind: Literal["DEMO"] = "DEMO"


class ClassroomGrant(ApiModel):
    active: bool
    role: Literal["student", "teacher"]


class Material(ApiModel):
    id: UUID
    title: str = Field(min_length=1, max_length=160)
    description: str = Field(max_length=2000)
    public_reference_url: str | None = None
    status: Literal["published", "archived"] = "published"

    @field_validator("public_reference_url")
    @classmethod
    def safe_public_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        parsed = urlsplit(value)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
            or not value.isascii()
            or any(character.isspace() for character in value)
        ):
            raise ValueError("Only a public HTTPS reference without credentials is allowed")
        try:
            _ = parsed.port
        except ValueError:
            raise ValueError("Invalid public reference port") from None
        return value


class Assignment(ApiModel):
    id: UUID
    title: str = Field(min_length=1, max_length=160)
    instructions: str = Field(min_length=1, max_length=5000)
    deadline_at: AwareDatetime
    status: Literal["draft", "published", "closed"]
    revision: int = Field(ge=1)

    @field_validator("deadline_at")
    @classmethod
    def to_utc(cls, value: datetime) -> datetime:
        return value.astimezone(UTC)


class QuestionInput(ApiModel):
    text: str = Field(min_length=1, max_length=2000)

    @field_validator("text")
    @classmethod
    def trim_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Text must not be blank")
        return value.strip()


class QuestionChange(QuestionInput):
    expected_revision: int = Field(ge=1)


class ResolutionInput(ApiModel):
    expected_revision: int = Field(ge=1)


class QuestionRecord(ApiModel):
    id: UUID
    author_id: UUID
    text: str
    answer: str | None = None
    state: Literal["open", "answered", "resolved"] = "open"
    visibility: Literal["teacher_only"] = "teacher_only"
    created_at: AwareDatetime
    revision: int = Field(ge=1)


class QuestionView(ApiModel):
    id: UUID
    text: str
    answer: str | None
    state: Literal["open", "answered", "resolved"]
    visibility: Literal["teacher_only"]
    created_at: AwareDatetime
    revision: int
    is_mine: bool


class SubmissionInput(QuestionInput):
    expected_revision: int = Field(ge=0)


class SubmissionView(ApiModel):
    assignment_id: UUID
    text: str
    state: Literal["submitted", "resubmitted"]
    submitted_at: AwareDatetime
    revision: int = Field(ge=1)
    source_kind: Literal["DEMO"] = "DEMO"


class ClassroomWorkspace(ApiModel):
    offering: Offering
    role: Literal["student", "teacher"]
    materials: list[Material]
    assignments: list[Assignment]
    questions: list[QuestionView]
    submissions: list[SubmissionView]
    source_kind: Literal["DEMO"] = "DEMO"
