from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, Field, field_validator

from app.schemas.common import ApiModel

EditableField = Literal["skills", "interests", "bio"]


class ProfileActor(ApiModel):
    user_id: UUID


class CurrentProfileAccess(ApiModel):
    user_id: UUID
    active: bool
    current_student: bool
    record_source: Literal["DEMO"] = "DEMO"


class ProfileEditPolicy(ApiModel):
    revision: int = Field(ge=1)
    editable_fields: frozenset[EditableField]
    record_source: Literal["DEMO"] = "DEMO"


class ActivityFields(ApiModel):
    skills: list[str] = Field(max_length=20)
    interests: list[str] = Field(max_length=20)
    bio: str = Field(max_length=500)

    @field_validator("skills", "interests")
    @classmethod
    def tags(cls, values: list[str]) -> list[str]:
        clean = [value.strip() for value in values]
        if any(not value or len(value) > 30 or any(ord(c) < 32 for c in value) for value in clean):
            raise ValueError("Tags must contain 1 to 30 characters")
        if len({value.casefold() for value in clean}) != len(clean):
            raise ValueError("Duplicate tags")
        return clean


class ActivityProfileRecord(ActivityFields):
    """Projection of the existing common/activity profile; never a second user ledger."""

    user_id: UUID
    display_name: str = Field(min_length=1, max_length=200)
    department_name: str = Field(min_length=1, max_length=200)
    academic_year: int = Field(ge=1, le=20)
    revision: int = Field(ge=1)
    updated_at: AwareDatetime
    record_source: Literal["DEMO"] = "DEMO"


class ProfileUpdate(ActivityFields):
    expected_revision: int = Field(ge=1)
    expected_policy_revision: int = Field(ge=1)


class ProfileView(ActivityFields):
    display_name: str
    department_name: str
    academic_year: int
    revision: int
    updated_at: AwareDatetime
    policy: ProfileEditPolicy
    record_source: Literal["DEMO"] = "DEMO"
    visibility: Literal["SELF_ONLY"] = "SELF_ONLY"
    identity_editable: Literal[False] = False
    replayed: bool = False
