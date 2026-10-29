from typing import Literal
from urllib.parse import urlsplit
from uuid import UUID

from pydantic import AwareDatetime, Field, field_validator, model_validator

from app.schemas.common import ApiModel

Kind = Literal["dorm", "inquiry", "volunteer"]
Choice = Literal[
    "demo_dorm_a",
    "demo_dorm_b",
    "process_information",
    "facility_information",
    "demo_volunteer_a",
    "demo_volunteer_b",
]
CHOICES = {
    "dorm": {"demo_dorm_a", "demo_dorm_b"},
    "inquiry": {"process_information", "facility_information"},
    "volunteer": {"demo_volunteer_a", "demo_volunteer_b"},
}
STATES = {
    "dorm": {"requested", "processing", "cancelled"},
    "inquiry": {"requested", "processing", "answered", "cancelled"},
    "volunteer": {"requested", "participating", "completed", "cancelled"},
}


class PublicLifeGuide(ApiModel):
    id: UUID
    category: Literal["dorm", "disability", "volunteer", "general_inquiry", "protected_help"]
    title: str = Field(min_length=1, max_length=200)
    summary: str = Field(min_length=1, max_length=1000)
    revision: int = Field(ge=1)
    source_kind: Literal["OFFICIAL_PUBLIC", "UNKNOWN", "DEMO"] = "UNKNOWN"
    source_url: str | None = Field(default=None, max_length=2048)
    checked_at: AwareDatetime | None = None

    @field_validator("source_url")
    @classmethod
    def safe_source(cls, value):
        if value is None:
            return None
        try:
            p = urlsplit(value)
            valid = p.scheme == "https" and p.hostname == "www.dit.ac.kr" and p.port is None
        except ValueError:
            raise ValueError("Invalid official URL") from None
        if (
            not valid
            or p.username is not None
            or p.password is not None
            or "\\" in value
            or not value.isascii()
            or any(c.isspace() or ord(c) < 32 or ord(c) == 127 for c in value)
        ):
            raise ValueError("Official HTTPS URL required")
        return value

    @model_validator(mode="after")
    def cited(self):
        if self.source_kind == "OFFICIAL_PUBLIC":
            if self.source_url is None or self.checked_at is None:
                raise ValueError("Official records require a URL and checked date")
        elif self.source_url is not None or self.checked_at is not None:
            raise ValueError("Unverified/demo records cannot borrow official evidence")
        return self


class GuidePage(ApiModel):
    items: list[PublicLifeGuide] = Field(max_length=50)
    offset: int = Field(ge=0)
    has_more: bool


class DemoLifePolicy(ApiModel):
    """Explicit fictional program rules; not institutional eligibility or dorm capacity."""

    program_id: UUID
    kind: Kind
    name: str = Field(min_length=1, max_length=100)
    revision: int = Field(ge=1)
    allowed_choices: list[Choice] = Field(min_length=1, max_length=6)
    opens_at: AwareDatetime
    closes_at: AwareDatetime
    cancel_until: AwareDatetime | None
    max_per_user: int = Field(ge=1, le=10)
    capacity: int = Field(ge=1, le=1000)
    source_kind: Literal["DEMO"] = "DEMO"

    @model_validator(mode="after")
    def valid_policy(self):
        if (
            self.closes_at <= self.opens_at
            or len(set(self.allowed_choices)) != len(self.allowed_choices)
            or not set(self.allowed_choices).issubset(CHOICES[self.kind])
        ):
            raise ValueError("Invalid fictional policy")
        return self


class LifeActor(ApiModel):
    user_id: UUID


class LifeGrant(ApiModel):
    """Latest verified identity/program access from a future approved server bridge."""

    active: bool
    program_ids: frozenset[UUID]


class CreateInput(ApiModel):
    program_id: UUID
    choice: Choice
    expected_policy_revision: int = Field(ge=1)


class ChangeInput(ApiModel):
    choice: Choice
    expected_revision: int = Field(ge=1)
    expected_policy_revision: int = Field(ge=1)


class CancelInput(ApiModel):
    expected_revision: int = Field(ge=1)
    expected_policy_revision: int = Field(ge=1)


class LifeRequestView(ApiModel):
    id: UUID
    program_id: UUID
    kind: Kind
    choice: Choice
    state: Literal["requested", "processing", "answered", "participating", "completed", "cancelled"]
    answer_code: Literal["demo_information_referred", "demo_information_checked"] | None = None
    revision: int = Field(ge=1)
    policy_revision: int = Field(ge=1)
    created_at: AwareDatetime
    updated_at: AwareDatetime
    source_kind: Literal["DEMO"] = "DEMO"
    official_effect: Literal[False] = False

    @model_validator(mode="after")
    def isolated_types(self):
        if self.choice not in CHOICES[self.kind] or self.state not in STATES[self.kind]:
            raise ValueError("Invalid request type/state")
        if (self.answer_code is not None) != (self.kind == "inquiry" and self.state == "answered"):
            raise ValueError("Only a fictional answered inquiry may carry an answer code")
        return self


class LifeRequestRecord(LifeRequestView):
    owner_id: UUID


class DemoBadgeView(ApiModel):
    id: UUID
    title: Literal["가상 참여 확인", "가상 학습 확인"]
    state: Literal["DEMO_ISSUED", "DEMO_REVOKED"]
    recorded_at: AwareDatetime
    source_kind: Literal["DEMO"] = "DEMO"
    official_effect: Literal[False] = False
    verification: Literal["NOT_OFFICIALLY_VERIFIABLE"] = "NOT_OFFICIALLY_VERIFIABLE"


class DemoBadgeRecord(DemoBadgeView):
    owner_id: UUID


class LifeOverview(ApiModel):
    requests: list[LifeRequestView] = Field(max_length=100)
    badges: list[DemoBadgeView] = Field(max_length=100)
    policies: list[DemoLifePolicy] = Field(max_length=20)
    source_kind: Literal["DEMO"] = "DEMO"
    sensitive_support: Literal["BLOCKED"] = "BLOCKED"
