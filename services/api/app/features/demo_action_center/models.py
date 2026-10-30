"""DTOs for the fictional DEMO action-center exercise (FR-HOME-001/003, FR-AI-001, FR-NOT-005).

Every value is fixed synthetic content kept in process memory. Nothing here is an academic
record, an official notice, a delivery receipt or proof of MariaDB persistence.
"""

from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import Field, StrictInt

from app.schemas.common import ApiModel


class DemoCardKind(StrEnum):
    CLASS = "CLASS"
    TASK = "TASK"
    NOTICE = "NOTICE"


class DemoCard(ApiModel):
    id: str = Field(pattern=r"^demo-(class|task|notice)-\d$")
    kind: DemoCardKind
    title: str = Field(min_length=1, max_length=80)
    detail: str = Field(min_length=1, max_length=160)
    link: str
    record_source: Literal["DEMO"] = "DEMO"


class DemoNotification(ApiModel):
    id: UUID
    card_id: str
    title: str = Field(min_length=1, max_length=80)
    link: str
    read: bool
    revision: int = Field(ge=1)
    delivery: Literal["IN_APP_ONLY"] = "IN_APP_ONLY"
    record_source: Literal["DEMO"] = "DEMO"


class DemoSummary(ApiModel):
    mode: Literal["DEMO"] = "DEMO"
    storage: Literal["PROCESS_MEMORY"] = "PROCESS_MEMORY"
    rule_based: Literal[True] = True
    ai_generated: Literal[False] = False
    school_connection: Literal["NOT_CONNECTED"] = "NOT_CONNECTED"
    cards: list[DemoCard]
    notifications: list[DemoNotification]
    unread_count: int = Field(ge=0)


class DemoReadInput(ApiModel):
    revision: StrictInt = Field(ge=1, le=1_000_000)


class DemoReadResult(ApiModel):
    notification: DemoNotification
    already_read: bool
    unread_count: int = Field(ge=0)
