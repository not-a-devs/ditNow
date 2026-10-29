"""DTOs for FR-OPP-002 matching and the rule-based FR-AI-002/003 subset.

Every response says how it was produced: deterministic server rules, no AI model, no
eligibility decision. Opportunity fields reuse the API-OPP projection DTOs unchanged.
"""

from enum import StrEnum
from typing import Literal

from pydantic import AwareDatetime, Field

from app.features.opportunities.schemas import (
    OpportunityDetailData,
    OpportunityKind,
    OpportunitySummaryData,
)
from app.schemas.common import ApiModel

GENERATOR = "deterministic_rules_v1"
PROVENANCE_NOTICE = (
    "서버의 고정 규칙으로 정렬한 참고 목록입니다. AI가 생성하지 않았으며 지원 자격을 "
    "보장하거나 판정하지 않습니다. 반드시 원문 공고를 확인하세요."
)


class ReasonCode(StrEnum):
    SCHOOL_WIDE = "SCHOOL_WIDE"
    DEPARTMENT_MATCH = "DEPARTMENT_MATCH"
    GRADE_MATCH = "GRADE_MATCH"
    KIND_INTEREST = "KIND_INTEREST"
    KEYWORD_INTEREST = "KEYWORD_INTEREST"
    DEADLINE_SOON = "DEADLINE_SOON"


class Window(StrEnum):
    UPCOMING = "UPCOMING"
    OPEN = "OPEN"
    CLOSED = "CLOSED"
    NO_DEADLINE = "NO_DEADLINE"


class Freshness(StrEnum):
    CURRENT = "CURRENT"
    STALE = "STALE"
    UNVERIFIED = "UNVERIFIED"


class CautionCode(StrEnum):
    NOT_ELIGIBILITY_DECISION = "NOT_ELIGIBILITY_DECISION"
    EXTERNAL_SUBMISSION = "EXTERNAL_SUBMISSION"
    DEMO_SOURCE = "DEMO_SOURCE"
    NEEDS_VERIFICATION = "NEEDS_VERIFICATION"
    STALE_SOURCE = "STALE_SOURCE"
    UNVERIFIED_SOURCE = "UNVERIFIED_SOURCE"
    DEADLINE_PASSED = "DEADLINE_PASSED"
    NOT_YET_OPEN = "NOT_YET_OPEN"
    OUT_OF_SCOPE = "OUT_OF_SCOPE"
    NO_APPLICATION_PROCEDURE = "NO_APPLICATION_PROCEDURE"


class StepCode(StrEnum):
    CHECK_ORIGINAL = "CHECK_ORIGINAL"
    DOWNLOAD_FORM = "DOWNLOAD_FORM"
    SUBMIT_TO_DESTINATION = "SUBMIT_TO_DESTINATION"
    APPLY_VIA_LINK = "APPLY_VIA_LINK"
    SELF_RECORD = "SELF_RECORD"


class Provenance(ApiModel):
    generator: Literal["deterministic_rules_v1"] = GENERATOR
    ai_generated: Literal[False] = False
    eligibility_guaranteed: Literal[False] = False
    notice: str = PROVENANCE_NOTICE


class MatchReason(ApiModel):
    code: ReasonCode
    # Which original catalog field (or caller input) produced this reason.
    source_field: str
    value: str | None = None


class MembershipData(ApiModel):
    department_code: str
    grade: int | None


class ContextBasis(ApiModel):
    """The actor's own current memberships and the interests sent with this request."""

    memberships: list[MembershipData]
    interest_kinds: list[OpportunityKind]
    interest_keywords: list[str]


class RecruitmentRef(ApiModel):
    id: str
    title: str
    field: str
    roles: list[str]
    deadline_at: AwareDatetime
    matched_keywords: list[str]


class RecruitmentRefs(ApiModel):
    status: Literal["NOT_CONNECTED", "AVAILABLE", "UNAVAILABLE"]
    open_count: int = 0
    items: list[RecruitmentRef] = Field(default_factory=list)


class MatchItem(ApiModel):
    opportunity: OpportunitySummaryData
    score: int
    reasons: list[MatchReason]
    window: Window
    freshness: Freshness
    checked_at: AwareDatetime | None
    source_url: str | None
    recruitment: RecruitmentRefs


class MatchPage(ApiModel):
    items: list[MatchItem]
    next_cursor: str | None
    candidate_cap: int
    candidates_scanned: int
    # False when the cap or a catalog paging fault stopped the scan before the end.
    complete: bool
    # Malformed catalog rows dropped from the result; no metadata about them is returned.
    omitted_count: int
    context: ContextBasis
    evaluated_at: AwareDatetime
    provenance: Provenance = Field(default_factory=Provenance)


class ProcedureStep(ApiModel):
    order: int
    code: StepCode
    available: bool
    evidence_field: str
    evidence_value: str | None = None
    evidence_url: str | None = None


class Caution(ApiModel):
    code: CautionCode


class MatchSummary(ApiModel):
    in_scope: bool
    score: int
    reasons: list[MatchReason]


class OpportunityBrief(ApiModel):
    """FR-AI-002 subset: original fields + fixed procedure template + evidence, no rewrite."""

    opportunity: OpportunityDetailData
    match: MatchSummary
    window: Window
    freshness: Freshness
    procedure: list[ProcedureStep]
    cautions: list[Caution]
    recruitment: RecruitmentRefs
    context: ContextBasis
    evaluated_at: AwareDatetime
    provenance: Provenance = Field(default_factory=Provenance)
