"""Demo activity-preference DTOs (FR-AUTH-003 sandbox only).

Requests forbid extra fields, so client-supplied ``user_id``/``name``/``bio``/``department``/
``role``/``academic_year``/``student_id`` are rejected with 400 instead of ignored. There is
deliberately no free-text field: interests are a fixed enum and the skill level is binary.
"""

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import Field, field_validator

from app.schemas.common import ApiModel

RECORD_SOURCE = "DEMO"
STORAGE = "PROCESS_MEMORY"


class DemoInterest(StrEnum):
    CODING = "coding"
    DESIGN = "design"
    VOLUNTEERING = "volunteering"
    CAREER = "career"


class SkillLevel(StrEnum):
    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"


INTEREST_ORDER = tuple(DemoInterest)
Revision = Annotated[int, Field(ge=1, le=1_000_000, strict=True)]


def canonical_interests(values: list[DemoInterest]) -> list[DemoInterest]:
    return [interest for interest in INTEREST_ORDER if interest in values]


class DemoProfileUpdate(ApiModel):
    """Full replacement of the caller's own preferences, guarded by the read ``revision``."""

    interests: Annotated[list[DemoInterest], Field(max_length=len(INTEREST_ORDER))]
    skill_level: SkillLevel
    revision: Revision

    @field_validator("interests")
    @classmethod
    def unique_interests(cls, values: list[DemoInterest]) -> list[DemoInterest]:
        if len(set(values)) != len(values):
            raise ValueError("duplicate interests are not allowed")
        return canonical_interests(values)


class DemoProfilePreferences(ApiModel):
    """Caller-only view. No identity, name, department, academic or role field exists."""

    interests: list[DemoInterest]
    skill_level: SkillLevel
    revision: int
    record_source: Literal["DEMO"] = RECORD_SOURCE
    storage: Literal["PROCESS_MEMORY"] = STORAGE
