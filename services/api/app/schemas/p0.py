"""Proposed P0 contracts only. No persistence, identity verification, or routes are implemented."""

from datetime import UTC, datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import AfterValidator, AwareDatetime, Field, HttpUrl, model_validator

from app.schemas.common import ApiModel, utc_now


def as_utc(value: datetime) -> datetime:
    return value.astimezone(UTC)


UtcDateTime = Annotated[AwareDatetime, AfterValidator(as_utc)]


class PublicOrigin(ApiModel):
    source_kind: Literal["OFFICIAL_PUBLIC"]
    source_url: HttpUrl
    checked_at: UtcDateTime


class DemoOrigin(ApiModel):
    source_kind: Literal["DEMO", "USER_DEMO"]
    label: Literal["시연용 가상 데이터"] = "시연용 가상 데이터"


DataOrigin = Annotated[PublicOrigin | DemoOrigin, Field(discriminator="source_kind")]


class PageRequest(ApiModel):
    limit: int = Field(default=20, ge=1, le=100)
    cursor: str | None = Field(default=None, min_length=1, max_length=512)


class PageResponse[T](ApiModel):
    data: list[T]
    next_cursor: str | None = None
    server_time: AwareDatetime = Field(default_factory=utc_now)


class Record(ApiModel):
    id: UUID
    revision: int = Field(ge=1)
    created_at: UtcDateTime
    updated_at: UtcDateTime

    @model_validator(mode="after")
    def chronological(self):
        if self.updated_at < self.created_at:
            raise ValueError("updated_at must not precede created_at")
        return self


class Identity(Record):
    issuer: str = Field(min_length=1, max_length=2048)
    subject: str = Field(min_length=1, max_length=512)
    status: Literal["pending", "active", "disabled"]
    origin: DemoOrigin


class Profile(ApiModel):
    user_id: UUID
    display_name: str = Field(min_length=1, max_length=100)
    origin: DemoOrigin


class Department(Record):
    code: str = Field(min_length=1, max_length=50)
    name: str = Field(min_length=1, max_length=100)
    origin: DataOrigin


class ValidPeriod(ApiModel):
    valid_from: UtcDateTime
    valid_to: UtcDateTime | None = None

    @model_validator(mode="after")
    def positive_period(self):
        if self.valid_to is not None and self.valid_to <= self.valid_from:
            raise ValueError("valid_to must follow valid_from")
        return self


class AcademicMembership(Record, ValidPeriod):
    user_id: UUID
    department_id: UUID
    academic_year: int = Field(ge=1)
    status: Literal["pending", "active", "inactive"]
    origin: DemoOrigin


class RoleAssignment(Record, ValidPeriod):
    user_id: UUID
    role: Literal["student", "professor", "assistant", "admin"]
    scope_type: Literal["platform", "department", "course_offering"]
    scope_id: UUID | None = None
    status: Literal["pending", "active", "revoked"]
    origin: DemoOrigin

    @model_validator(mode="after")
    def valid_scope(self):
        if (self.scope_type == "platform") != (self.scope_id is None):
            raise ValueError("platform scope has no ID; other scopes require an ID")
        return self


class AnonymousPostCreate(ApiModel):
    title: str = Field(min_length=2, max_length=120)
    body: str = Field(min_length=1, max_length=5000)


class AnonymousPostPrivate(Record, AnonymousPostCreate):
    author_id: UUID
    status: Literal["active", "hidden", "deleted"]
    origin: DemoOrigin


class AnonymousPostPublic(Record, AnonymousPostCreate):
    comment_count: int = Field(ge=0)
    is_mine: bool
    origin: DemoOrigin


class RecruitmentCreate(ApiModel):
    title: str = Field(min_length=2, max_length=120)
    body: str = Field(min_length=1, max_length=5000)
    capacity: int = Field(ge=2, le=20, description="Proposed MVP default, includes the owner")
    deadline_at: UtcDateTime
    opportunity_id: UUID | None = None


class Recruitment(Record, RecruitmentCreate):
    owner_id: UUID
    status: Literal["open", "closed", "cancelled"]
    origin: DemoOrigin


class Opportunity(Record):
    kind: Literal["장학금", "근로", "공모전", "취업", "행사"]
    title: str = Field(min_length=1, max_length=120)
    deadline_at: UtcDateTime
    submission_mode: Literal["external_document_submission", "external_link", "info_only"]
    destination: str | None = Field(default=None, max_length=1000)
    origin: DataOrigin


class SavedOpportunity(Record):
    user_id: UUID
    opportunity_id: UUID
    status: Literal["interested", "preparing", "self_reported_submitted", "closed"]
    memo: str = Field(default="", max_length=5000)
    self_reported_submitted_at: UtcDateTime | None = None
    origin: DemoOrigin

    @model_validator(mode="after")
    def self_report_is_dated(self):
        if self.status == "self_reported_submitted" and self.self_reported_submitted_at is None:
            raise ValueError("self-reported submission requires its own timestamp")
        return self


class OpportunityCheckItem(Record):
    saved_opportunity_id: UUID
    text: str = Field(min_length=1, max_length=500)
    completed_at: UtcDateTime | None = None
    sort_order: int = Field(ge=0)


class GeneralAuditLog(Record):
    event: str = Field(min_length=1, max_length=100)
    resource_kind: Literal[
        "identity", "membership", "role", "anonymous_post", "recruitment", "opportunity"
    ]
    actor_id: UUID | None = None
    entity_id: UUID | None = None

    @model_validator(mode="after")
    def no_anonymous_identity_map(self):
        if self.resource_kind == "anonymous_post" and self.actor_id and self.entity_id:
            raise ValueError("anonymous identity mappings cannot enter the general audit model")
        return self
