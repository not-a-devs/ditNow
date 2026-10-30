from dataclasses import dataclass
from enum import StrEnum
from typing import Annotated, Literal
from uuid import UUID

from pydantic import AwareDatetime, ConfigDict, Field, StrictBool, field_validator

from app.schemas.common import ApiModel


class DemoKind(StrEnum):
    ADMISSION_RESULT = "ADMISSION_RESULT"
    ADMISSION_WITHDRAWAL = "ADMISSION_WITHDRAWAL"
    CERTIFICATE = "CERTIFICATE"
    TUITION = "TUITION"
    PROTECTED_COUNSEL = "PROTECTED_COUNSEL"


class DemoScenario(StrEnum):
    STANDARD = "STANDARD"
    REVIEW_EXAMPLE = "REVIEW_EXAMPLE"


class DemoStatus(StrEnum):
    REQUESTED = "REQUESTED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"


Revision = Annotated[int, Field(strict=True, ge=1, le=2_147_483_647)]


@dataclass(frozen=True, slots=True)
class DemoActor:
    """Server-resolved current common identity, never constructed from request-body claims."""

    user_id: UUID


class CreateInput(ApiModel):
    kind: DemoKind
    scenario: DemoScenario
    consent: StrictBool

    @field_validator("consent")
    @classmethod
    def explicit_consent(cls, value: bool) -> bool:
        if not value:
            raise ValueError("Explicit fictional-service consent required")
        return value


class AdvanceInput(ApiModel):
    revision: Revision


class DemoItem(ApiModel):
    model_config = ConfigDict(frozen=True)

    id: UUID
    kind: DemoKind
    scenario: DemoScenario
    status: DemoStatus
    status_label: str
    title: str
    revision: Revision
    created_at: AwareDatetime
    updated_at: AwareDatetime
    outcome_text: str | None = None
    document_text: str | None = None
    source_kind: Literal["DEMO"] = "DEMO"
    persistence: Literal["PROCESS_MEMORY"] = "PROCESS_MEMORY"
    official_effect: Literal[False] = False
    sensitive_content_collected: Literal[False] = False


class DemoPage(ApiModel):
    source_kind: Literal["DEMO"] = "DEMO"
    persistence: Literal["PROCESS_MEMORY"] = "PROCESS_MEMORY"
    official_effect: Literal[False] = False
    items: list[DemoItem]


class DeletedDemo(ApiModel):
    id: UUID
    deleted: Literal[True] = True
