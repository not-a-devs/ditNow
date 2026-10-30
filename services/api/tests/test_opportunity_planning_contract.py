"""Offline phase-2 schemas. No real or fake LLM invocation and no persistence."""

from uuid import uuid4

import pytest
from pydantic import ValidationError
from test_opportunity_matching_support import USER_A, USER_B, FakeCatalog, make_opportunity, service

from app.features.opportunities.repository import TargetScope
from app.features.opportunity_matching.planning_contract import (
    PreparationPlanningInput,
    planning_input,
    validate_planning_output,
)
from app.features.opportunity_matching.service import Interests


def source():
    opportunity = make_opportunity()
    brief = service(FakeCatalog([opportunity])).brief(USER_A, opportunity.id, Interests())
    return planning_input(brief)


def output(value):
    return {
        "opportunity_id": str(value.opportunity_id),
        "summary": "원문 지원 조건을 확인하고 준비하세요.",
        "actions": [
            {
                "title": "원문 확인",
                "reason": "지원 조건 확인이 필요합니다.",
                "evidence_refs": ["title"],
            }
        ],
    }


def test_allowlisted_input_excludes_personal_context_and_instructions():
    data = source().model_dump(mode="json")
    assert set(data) == {
        "contract",
        "opportunity_id",
        "source_kind",
        "evidence",
    }
    assert set(item["ref"] for item in data["evidence"]) <= {
        "title",
        "organization",
        "eligibility",
        "submission_mode",
        "deadline_at",
    }
    assert str(USER_A) not in str(data)
    assert "CSE" not in str(data)  # A's canonical department is not a model input.


def test_valid_draft_remains_confirmation_only():
    value = source()
    draft = validate_planning_output(value, output(value))
    assert draft.requires_user_confirmation is True
    assert draft.eligibility_guaranteed is False


@pytest.mark.parametrize(
    "extra", ["token", "user_id", "memberships", "question", "interests", "rule_reason_codes"]
)
def test_input_rejects_extra_personal_fields(extra):
    with pytest.raises(ValidationError):
        PreparationPlanningInput.model_validate(source().model_dump() | {extra: "not-allowed"})


def test_same_public_notice_never_exports_membership_match_inference():
    opportunity = make_opportunity(target_scope=TargetScope("grade", ("CSE",), (2,)))
    matching = service(FakeCatalog([opportunity]))
    a = matching.brief(USER_A, opportunity.id, Interests())
    b = matching.brief(USER_B, opportunity.id, Interests())
    assert a.match.in_scope and not b.match.in_scope
    # Match signals combined with public eligibility could reveal membership. Export neither.
    assert planning_input(a).model_dump() == planning_input(b).model_dump()


@pytest.mark.parametrize(
    "patch",
    [
        {"opportunity_id": str(uuid4())},
        {"eligibility_guaranteed": True},
        {"requires_user_confirmation": False},
        {"post_now": True},
    ],
)
def test_draft_rejects_forged_sources_authority_and_tools(patch):
    value = source()
    with pytest.raises((ValueError, ValidationError)):
        validate_planning_output(value, output(value) | patch)


def test_unknown_or_missing_evidence_is_rejected():
    value = source()
    raw = output(value)
    raw["actions"][0]["evidence_refs"] = ["invented_source"]
    with pytest.raises(ValidationError):
        validate_planning_output(value, raw)
    # A syntactically allowed field must also exist in this exact source snapshot.
    restricted = value.model_copy(update={"evidence": value.evidence[:1]})
    raw["actions"][0]["evidence_refs"] = ["submission_mode"]
    with pytest.raises(ValueError, match="evidence mismatch"):
        validate_planning_output(restricted, raw)


def test_model_cannot_return_an_arbitrary_url_or_save_payload():
    value = source()
    raw = output(value)
    raw["actions"][0]["url"] = "https://untrusted.example.test"
    with pytest.raises(ValidationError):
        validate_planning_output(value, raw)
