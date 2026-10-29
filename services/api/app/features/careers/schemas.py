"""API-JOB DTOs. Request models forbid extra fields, so client `user_id`/`owner_id`/`status`/
`name`/`phone`/`email`/`file` keys are rejected (400) instead of ignored."""

from typing import Annotated, Literal
from uuid import UUID

from pydantic import AfterValidator, AwareDatetime, Field, StringConstraints

from app.features.careers.domain import (
    ApplicationStatus,
    EmploymentType,
    Provenance,
    reject_contact_details,
    reject_controls,
)
from app.schemas.common import ApiModel


def _text(min_length: int, max_length: int):
    # Newline is the only control char reject_controls allows; _single_line removes it.
    return Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=min_length, max_length=max_length),
        AfterValidator(reject_controls),
        AfterValidator(reject_contact_details),
    ]


def _single_line(value: str) -> str:
    if "\n" in value:
        raise ValueError("single line only")
    return value


Alias = Annotated[_text(2, 30), AfterValidator(_single_line)]
Label = Annotated[_text(1, 30), AfterValidator(_single_line)]
Summary = _text(0, 500)
Note = _text(0, 200)
Title = Annotated[_text(2, 80), AfterValidator(_single_line)]
Description = _text(1, 2000)


# ---- FR-JOB-001 public jobs / FR-OPP-005 contest candidates ----


class JobSummaryData(ApiModel):
    id: UUID
    title: str
    organization: str
    department_codes: list[str]
    apply_starts_at: AwareDatetime | None
    deadline_at: AwareDatetime | None
    deadline_passed: bool
    provenance: Provenance
    original_url: str | None
    checked_at: AwareDatetime | None
    # The platform never receives job applications or confirms employment.
    platform_receives_application: Literal[False] = False


class JobPageData(ApiModel):
    items: list[JobSummaryData]
    next_cursor: str | None


class ContestCandidateData(ApiModel):
    opportunity_id: UUID
    title: str
    organization: str
    deadline_at: AwareDatetime | None
    provenance: Provenance
    original_url: str | None
    checked_at: AwareDatetime | None
    # True when community may accept `opportunity_id` on a recruitment (ID reference only).
    team_link_candidate: bool
    reference_field: Literal["opportunity_id"] = "opportunity_id"


class ContestPageData(ApiModel):
    items: list[ContestCandidateData]
    next_cursor: str | None


# ---- FR-JOB-002 virtual career profile ----


class ProfileCreate(ApiModel):
    alias: Alias
    desired_roles: Annotated[list[Label], Field(max_length=5)] = Field(default_factory=list)
    skills: Annotated[list[Label], Field(max_length=20)] = Field(default_factory=list)
    summary: Summary = ""


class ProfilePatch(ApiModel):
    alias: Alias | None = None
    desired_roles: Annotated[list[Label], Field(max_length=5)] | None = None
    skills: Annotated[list[Label], Field(max_length=20)] | None = None
    summary: Summary | None = None


class ProfileData(ApiModel):
    id: UUID
    alias: str
    desired_roles: list[str]
    skills: list[str]
    summary: str
    revision: int
    created_at: AwareDatetime
    updated_at: AwareDatetime
    # Sharing with counsellors/employers needs consent policy (OPEN-R09~R13): BLOCKED.
    shared_with: list[str] = Field(default_factory=list)
    is_virtual: Literal[True] = True


class ProfileEnvelope(ApiModel):
    profile: ProfileData | None


# ---- FR-JOB-003 / FR-OPP-006 virtual program applications ----


class ProgramData(ApiModel):
    id: UUID
    title: str
    host: str
    summary: str
    capacity: int | None
    apply_starts_at: AwareDatetime | None
    apply_ends_at: AwareDatetime | None
    window_open: bool
    provenance: Provenance
    source_url: str | None
    checked_at: AwareDatetime | None
    # Only DEMO programs accept virtual applications; official ones are information only.
    accepts_virtual_application: bool


class ProgramListData(ApiModel):
    items: list[ProgramData]
    policy_id: str
    policy_basis: Literal["DEMO"] = "DEMO"


class ApplicationCreate(ApiModel):
    note: Note = ""


class ApplicationCancel(ApiModel):
    pass


class ApplicationData(ApiModel):
    id: UUID
    program_id: UUID
    status: ApplicationStatus
    note: str
    revision: int
    created_at: AwareDatetime
    updated_at: AwareDatetime
    cancelled_at: AwareDatetime | None
    # Real review/selection is BLOCKED; this is never an acceptance result.
    review_status: Literal["not_reviewed"] = "not_reviewed"
    is_virtual: Literal[True] = True
    program: ProgramData | None


class ApplicationListData(ApiModel):
    items: list[ApplicationData]


# ---- FR-JOB-004 employer request drafts ----


class EmployerDraftCreate(ApiModel):
    company_alias: Alias
    role_title: Title
    description: Description
    employment_type: EmploymentType
    closes_at: AwareDatetime


class EmployerDraftPatch(ApiModel):
    company_alias: Alias | None = None
    role_title: Title | None = None
    description: Description | None = None
    employment_type: EmploymentType | None = None
    closes_at: AwareDatetime | None = None


class EmployerDraftData(ApiModel):
    id: UUID
    company_alias: str
    role_title: str
    description: str
    employment_type: EmploymentType
    closes_at: AwareDatetime
    revision: int
    created_at: AwareDatetime
    updated_at: AwareDatetime
    # Submission/review/publication and employer accounts are BLOCKED.
    status: Literal["draft"] = "draft"
    publishable: Literal[False] = False


class EmployerDraftListData(ApiModel):
    items: list[EmployerDraftData]


class DeletedData(ApiModel):
    id: UUID
    deleted: Literal[True] = True
