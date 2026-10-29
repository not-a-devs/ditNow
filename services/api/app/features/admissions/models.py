from datetime import UTC, datetime
from typing import Literal
from urllib.parse import urlsplit
from uuid import UUID

from pydantic import AwareDatetime, Field, field_validator, model_validator

from app.schemas.common import ApiModel

Alias = Literal["가상 지원자 A", "가상 지원자 B", "가상 지원자 C"]
Motivation = Literal["career_exploration", "skill_growth", "project_learning"]
ApplicationState = Literal["draft", "submitted", "received", "withdrawal_requested"]


class Citation(ApiModel):
    source_kind: Literal["OFFICIAL_PUBLIC", "DEMO", "UNKNOWN"] = "UNKNOWN"
    source_url: str | None = Field(default=None, max_length=2048)
    checked_at: AwareDatetime | None = None

    @field_validator("source_url")
    @classmethod
    def safe_source(cls, value: str | None):
        if value is None:
            return None
        try:
            parsed = urlsplit(value)
            port = parsed.port
            valid = parsed.scheme in {"http", "https"} and parsed.hostname
        except ValueError:
            raise ValueError("Invalid public source") from None
        if (
            not valid
            or port == 0
            or parsed.username is not None
            or parsed.password is not None
            or not value.isascii()
            or any(c.isspace() or ord(c) < 32 or ord(c) == 127 for c in value)
            or "\\" in value
        ):
            raise ValueError("Safe HTTP source required")
        return value

    @model_validator(mode="after")
    def complete_citation(self):
        if self.source_kind == "OFFICIAL_PUBLIC" and (
            self.source_url is None or self.checked_at is None
        ):
            raise ValueError("Official material requires a URL and checked date")
        if self.source_kind != "OFFICIAL_PUBLIC" and (
            self.source_url is not None or self.checked_at is not None
        ):
            raise ValueError("Unverified and demo material must not borrow an official citation")
        return self


class GuideSchedule(ApiModel):
    label: str = Field(min_length=1, max_length=100)
    starts_at: AwareDatetime
    ends_at: AwareDatetime

    @model_validator(mode="after")
    def ordered(self):
        if self.ends_at <= self.starts_at:
            raise ValueError("Schedule must have a positive interval")
        return self


class GuideFAQ(ApiModel):
    question: str = Field(min_length=1, max_length=200)
    answer: str = Field(min_length=1, max_length=1000)


class AdmissionGuide(Citation):
    id: UUID
    title: str = Field(min_length=1, max_length=200)
    summary: str = Field(max_length=1000)
    revision: int = Field(ge=1)
    schedules: list[GuideSchedule] = Field(default_factory=list, max_length=30)
    faqs: list[GuideFAQ] = Field(default_factory=list, max_length=30)


class GuidePage(ApiModel):
    items: list[AdmissionGuide] = Field(max_length=50)
    offset: int = Field(ge=0)
    has_more: bool


class DemoTrack(ApiModel):
    id: UUID
    label: str = Field(min_length=1, max_length=100)


class DemoAdmissionPolicy(ApiModel):
    """Explicit test/demo policy, never DIT institutional admission rules."""

    cycle_id: UUID
    name: str = Field(min_length=1, max_length=100)
    revision: int = Field(ge=1)
    tracks: list[DemoTrack] = Field(min_length=1, max_length=20)
    opens_at: AwareDatetime
    closes_at: AwareDatetime
    withdrawal_closes_at: AwareDatetime | None
    max_applications: int = Field(ge=1, le=20)
    source_kind: Literal["DEMO"] = "DEMO"

    @model_validator(mode="after")
    def valid_policy(self):
        if self.closes_at <= self.opens_at or len({t.id for t in self.tracks}) != len(self.tracks):
            raise ValueError("Invalid demo policy")
        return self


class ApplicantActor(ApiModel):
    """Server bridge input only; not a new role or authentication provider."""

    user_id: UUID


class ApplicantGrant(ApiModel):
    """Adapter re-reads current verified identity and applicant eligibility per transaction."""

    active: bool
    applicant: bool
    cycle_ids: frozenset[UUID]


class DraftFields(ApiModel):
    demo_alias: Alias
    track_id: UUID
    motivation: Motivation
    expected_policy_revision: int = Field(ge=1)


class DraftCreate(DraftFields):
    cycle_id: UUID


class DraftUpdate(DraftFields):
    expected_revision: int = Field(ge=1)


class TransitionInput(ApiModel):
    expected_revision: int = Field(ge=1)
    expected_policy_revision: int = Field(ge=1)


class ApplicationView(ApiModel):
    id: UUID
    cycle_id: UUID
    demo_alias: Alias
    track_id: UUID
    motivation: Motivation
    state: ApplicationState
    revision: int = Field(ge=1)
    policy_revision: int = Field(ge=1)
    created_at: AwareDatetime
    updated_at: AwareDatetime
    source_kind: Literal["DEMO"] = "DEMO"
    documents: Literal["BLOCKED"] = "BLOCKED"
    admission_result: Literal["BLOCKED"] = "BLOCKED"
    payment_refund: Literal["BLOCKED"] = "BLOCKED"

    @field_validator("created_at", "updated_at")
    @classmethod
    def utc_time(cls, value: datetime):
        return value.astimezone(UTC)


class ApplicationRecord(ApplicationView):
    owner_id: UUID


class ApplicantOverview(ApiModel):
    applications: list[ApplicationView] = Field(max_length=100)
    policies: list[DemoAdmissionPolicy] = Field(max_length=20)
    source_kind: Literal["DEMO"] = "DEMO"
