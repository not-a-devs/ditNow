"""Phase-2 LLM contract only. No provider, model invocation, tool or database write.

Build solely from the public opportunity projection. Never include match signals,
the question, interests, current membership values, user identity or saved data.
Public catalog text remains untrusted data. Production calls need separate approval.
"""

from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, StringConstraints

from app.features.opportunity_matching.models import OpportunityBrief
from app.schemas.common import ApiModel

ShortText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
EvidenceText = Annotated[str, StringConstraints(min_length=1, max_length=4000)]
EvidenceId = Literal["title", "organization", "eligibility", "submission_mode", "deadline_at"]


class PlanningEvidence(ApiModel):
    ref: EvidenceId
    value: EvidenceText


class PreparationPlanningInput(ApiModel):
    contract: Literal["opportunity_preparation_v1"] = "opportunity_preparation_v1"
    opportunity_id: UUID
    source_kind: Literal["OFFICIAL_PUBLIC", "DEMO"]
    evidence: list[PlanningEvidence] = Field(min_length=1, max_length=5)


class PreparationActionDraft(ApiModel):
    title: ShortText
    reason: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
    evidence_refs: list[EvidenceId] = Field(min_length=1, max_length=5)


class PreparationPlanningOutput(ApiModel):
    """Text draft, never a save/post instruction. Not used by the rule-based UI."""

    contract: Literal["opportunity_preparation_v1"] = "opportunity_preparation_v1"
    opportunity_id: UUID
    summary: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]
    actions: list[PreparationActionDraft] = Field(min_length=1, max_length=8)
    eligibility_guaranteed: Literal[False] = False
    requires_user_confirmation: Literal[True] = True


def planning_input(brief: OpportunityBrief) -> PreparationPlanningInput:
    """Explicit allowlist: no serialization of the personalized brief as a whole."""
    opportunity = brief.opportunity
    values = {
        "title": opportunity.title,
        "organization": opportunity.organization,
        "eligibility": opportunity.eligibility,
        "submission_mode": opportunity.submission_mode.value,
        "deadline_at": opportunity.deadline_at.isoformat() if opportunity.deadline_at else None,
    }
    return PreparationPlanningInput(
        opportunity_id=opportunity.id,
        source_kind=opportunity.source_kind.value,
        evidence=[
            PlanningEvidence(ref=ref, value=value)
            for ref, value in values.items()
            if value and value.strip()
        ],
    )


def validate_planning_output(
    source: PreparationPlanningInput, raw: object
) -> PreparationPlanningOutput:
    result = PreparationPlanningOutput.model_validate(raw)
    if result.opportunity_id != source.opportunity_id:
        raise ValueError("Planning source mismatch")
    known = {item.ref for item in source.evidence}
    if any(not set(action.evidence_refs) <= known for action in result.actions):
        raise ValueError("Planning evidence mismatch")
    return result
