from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, ConfigDict, Field, StrictBool, field_validator

from app.schemas.common import ApiModel

ID_PATTERN = r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
KEY_PATTERN = r"^[A-Za-z0-9-]{16,100}$"
REVISION_MAX = 1_000_000


class TargetCode(StrEnum):
    """Fixed fictional targets; never a real user id or lookup."""

    STUDENT_DEMO_A = "STUDENT_DEMO_A"
    STUDENT_DEMO_B = "STUDENT_DEMO_B"


class ProposalScope(StrEnum):
    DEPARTMENT_STUDENT = "DEPARTMENT_STUDENT"
    YEAR_STUDENT = "YEAR_STUDENT"


class ReasonCode(StrEnum):
    ACADEMIC_DEMO = "ACADEMIC_DEMO"
    CORRECTION_DEMO = "CORRECTION_DEMO"


class ProposalState(StrEnum):
    DRAFT = "DRAFT"
    SUBMITTED = "SUBMITTED"
    WITHDRAWN = "WITHDRAWN"


@dataclass(frozen=True)
class AdminChangeActor:
    """Built only by the trusted server auth owner; never from client input."""

    user_id: UUID
    can_manage: bool


class StrictBody(ApiModel):
    # Model-wide strict would reject normal JSON enum strings; strictness is per field instead.
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)


class ProposalCreate(StrictBody):
    # Enums accept only their exact string values (no coercion of other types).
    target_code: TargetCode
    proposal_scope: ProposalScope
    reason_code: ReasonCode
    # StrictBool rejects 1/"true"; the validator then requires the literal True.
    consent: StrictBool

    @field_validator("consent")
    @classmethod
    def _consent_true(cls, value: bool) -> bool:
        if value is not True:
            raise ValueError("consent must be true")
        return value


class ProposalSubmit(StrictBody):
    expected_revision: int = Field(strict=True, ge=1, le=REVISION_MAX)


@dataclass
class ProposalRecord:
    id: str
    owner_id: UUID
    target_code: TargetCode
    proposal_scope: ProposalScope
    reason_code: ReasonCode
    state: ProposalState
    revision: int
    created_at: datetime
    updated_at: datetime
    submitted_at: datetime | None = None
    withdrawn_at: datetime | None = None


class ProposalView(ApiModel):
    id: str
    target_code: TargetCode
    proposal_scope: ProposalScope
    reason_code: ReasonCode
    state: ProposalState
    revision: int = Field(ge=1)
    created_at: AwareDatetime
    updated_at: AwareDatetime
    submitted_at: AwareDatetime | None
    withdrawn_at: AwareDatetime | None
    record_source: Literal["DEMO"] = "DEMO"
    storage: Literal["PROCESS_MEMORY"] = "PROCESS_MEMORY"
    official_effect: Literal[False] = False
    restart_reset: Literal[True] = True
    replayed: bool = False


class ProposalList(ApiModel):
    items: list[ProposalView]
    owner_cap: int = Field(ge=1)
    record_source: Literal["DEMO"] = "DEMO"
    storage: Literal["PROCESS_MEMORY"] = "PROCESS_MEMORY"
    official_effect: Literal[False] = False
    restart_reset: Literal[True] = True
