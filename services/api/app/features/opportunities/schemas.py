"""API-OPP DTOs (FR-OPP-001~004). Public projection and owner-only preparation records."""

from datetime import datetime
from enum import StrEnum
from typing import Annotated
from uuid import UUID

from pydantic import AwareDatetime, Field, StringConstraints

from app.schemas.common import ApiModel


class OpportunityKind(StrEnum):
    SCHOLARSHIP = "scholarship"
    WORK_STUDY = "work_study"
    CAREER = "career"
    CONTEST = "contest"
    EVENT = "event"


class SubmissionMode(StrEnum):
    # DEC-013: external scholarships are downloaded and submitted directly to the institution.
    EXTERNAL_DOCUMENT_SUBMISSION = "external_document_submission"
    EXTERNAL_LINK = "external_link"
    INFO_ONLY = "info_only"


class SourceKind(StrEnum):
    # Subset of the shared provenance enum (docs/v1-draft/05_DB_API.md). USER_DEMO is excluded:
    # the catalog only exposes admin-approved records. See repository.source_kind_from_storage.
    OFFICIAL_PUBLIC = "OFFICIAL_PUBLIC"
    DEMO = "DEMO"


class PublicationStatus(StrEnum):
    DRAFT = "draft"
    PUBLISHED = "published"
    ARCHIVED = "archived"


class PreparationStatus(StrEnum):
    # FR-OPP-004 / NFR-DATA-002: self_reported_submitted is the user's own record only.
    INTERESTED = "interested"
    PREPARING = "preparing"
    SELF_REPORTED_SUBMITTED = "self_reported_submitted"
    CLOSED = "closed"


class TargetScopeData(ApiModel):
    level: Annotated[str, Field(pattern="^(school|department|grade)$")]
    department_codes: list[str] = Field(default_factory=list)
    academic_years: list[int] = Field(default_factory=list)


class OpportunityFileData(ApiModel):
    filename: str
    original_url: str | None
    checked_at: AwareDatetime | None


class OpportunitySummaryData(ApiModel):
    id: UUID
    kind: OpportunityKind
    title: str
    organization: str
    target_scope: TargetScopeData
    apply_starts_at: AwareDatetime | None
    deadline_at: AwareDatetime | None
    deadline_passed: bool
    submission_mode: SubmissionMode
    source_kind: SourceKind
    needs_verification: bool


class OpportunityDetailData(OpportunitySummaryData):
    eligibility: str
    destination: str | None
    original_url: str | None
    source_url: str | None
    checked_at: AwareDatetime | None
    files: list[OpportunityFileData]
    # Always false: this platform never receives or confirms external submissions.
    platform_receives_submission: bool = False


class OpportunityPageData(ApiModel):
    items: list[OpportunitySummaryData]
    next_cursor: str | None


Text200 = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Memo = Annotated[str, StringConstraints(strip_whitespace=True, max_length=1000)]
SortOrder = Annotated[int, Field(ge=0, le=999)]


class SaveOpportunityRequest(ApiModel):
    memo: Memo = ""


class SavedOpportunityPatch(ApiModel):
    status: PreparationStatus | None = None
    memo: Memo | None = None


class CheckItemCreate(ApiModel):
    text: Text200
    sort_order: SortOrder


class CheckItemPatch(ApiModel):
    text: Text200 | None = None
    sort_order: SortOrder | None = None
    completed: bool | None = None


class CheckItemData(ApiModel):
    id: UUID
    text: str
    sort_order: int
    completed_at: AwareDatetime | None
    revision: int


class SavedOpportunityData(ApiModel):
    opportunity_id: UUID
    status: PreparationStatus
    memo: str
    self_reported_submitted_at: AwareDatetime | None
    revision: int
    created_at: datetime
    updated_at: datetime
    checks: list[CheckItemData]
    # None when the source opportunity is no longer publicly visible.
    opportunity: OpportunitySummaryData | None


class SavedOpportunityListData(ApiModel):
    items: list[SavedOpportunityData]


class DeletedData(ApiModel):
    deleted: bool
