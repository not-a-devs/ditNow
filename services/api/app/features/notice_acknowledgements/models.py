from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, field_validator


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class _Demo(_Strict):
    """Every response states it is a restart-reset DEMO record without official effect."""

    record_source: Literal["DEMO"] = "DEMO"
    storage: Literal["PROCESS_MEMORY"] = "PROCESS_MEMORY"
    official_effect: Literal[False] = False
    restart_reset: Literal[True] = True


class AckRequestInput(_Strict):
    notice_id: UUID
    opt_in: StrictBool
    # Expected acknowledgement-request revision: omitted = create or return current,
    # 0 = must not exist yet, N = must equal the current request revision.
    revision: StrictInt | None = Field(default=None, ge=0, le=1_000_000)

    @field_validator("opt_in")
    @classmethod
    def _explicit_opt_in(cls, value: bool) -> bool:
        if value is not True:
            raise ValueError("opt_in must be true")
        return value


class AckInput(_Strict):
    request_revision: StrictInt = Field(ge=1, le=1_000_000)


class AckRequestView(_Demo):
    notice_id: UUID
    request_revision: int


class OwnState(_Demo):
    notice_id: UUID
    requested: bool
    request_revision: int | None
    can_request: bool
    can_acknowledge: bool
    acknowledged: bool
    acknowledged_at: datetime | None
    can_view_summary: bool


class AckReceipt(_Demo):
    notice_id: UUID
    request_revision: int
    acknowledged: Literal[True] = True
    acknowledged_at: datetime


class AckSummary(_Demo):
    notice_id: UUID
    request_revision: int
    eligible_total: int
    acknowledged_count: int
    audience_basis: Literal["TRUSTED_PORT_CURRENT"] = "TRUSTED_PORT_CURRENT"
