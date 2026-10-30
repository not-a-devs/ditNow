from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import ConfigDict, Field, model_validator

from app.schemas.common import ApiModel


class AuditActor(ApiModel):
    """Trusted server-resolved actor. Never built from client-supplied owner or role fields."""

    user_id: UUID


class AuditCategory(StrEnum):
    NOTICE = "NOTICE"
    POST = "POST"
    REPORT = "REPORT"


class AuditStatus(StrEnum):
    PENDING = "PENDING"
    CLASSIFIED = "CLASSIFIED"
    RESOLVED = "RESOLVED"


class Classification(StrEnum):
    REVIEW_NEEDED = "REVIEW_NEEDED"
    NO_ACTION = "NO_ACTION"


class Resolution(StrEnum):
    KEEP_DEMO = "KEEP_DEMO"
    RESOLVE_DEMO = "RESOLVE_DEMO"


class NoteCode(StrEnum):
    DEMO_CHECKED = "DEMO_CHECKED"
    DEMO_POLICY_REVIEW = "DEMO_POLICY_REVIEW"


class DemoMeta(ApiModel):
    source_kind: Literal["DEMO"] = "DEMO"
    storage: Literal["PROCESS_MEMORY"] = "PROCESS_MEMORY"
    official_effect: Literal[False] = False
    restart_reset: Literal[True] = True


class AuditItemView(ApiModel):
    """Minimal fixed metadata only: no author identity, name, content body or report text."""

    id: UUID
    category: AuditCategory
    demo_label: str = Field(pattern=r"^DEMO_ITEM_[0-9]{2}$")
    status: AuditStatus
    classification: Classification | None
    resolution: Resolution | None
    note_code: NoteCode | None
    revision: int = Field(ge=1)
    meta: DemoMeta = Field(default_factory=DemoMeta)


class AuditQueuePage(ApiModel):
    items: list[AuditItemView] = Field(max_length=20)
    meta: DemoMeta = Field(default_factory=DemoMeta)


class AuditPatchInput(ApiModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    # Field-level strict: FastAPI validates parsed JSON in python mode, where model-wide strict
    # would reject enum strings. Enums still only accept their exact values.
    revision: int = Field(strict=True, ge=1, le=1_000_000)
    classification: Classification | None = None
    resolution: Resolution | None = None
    note_code: NoteCode

    @model_validator(mode="after")
    def exactly_one_step(self) -> "AuditPatchInput":
        if (self.classification is None) == (self.resolution is None):
            raise ValueError("exactly one of classification or resolution")
        return self
