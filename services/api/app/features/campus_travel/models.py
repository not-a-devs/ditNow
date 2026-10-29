import re
from datetime import UTC
from typing import Literal

from pydantic import AwareDatetime, Field, field_validator, model_validator

from app.schemas.common import ApiModel

NOTICE = (
    "사용자가 입력한 시각과 예상 이동 시간만 계산합니다. 실제 지도·최단 경로·공식 이동 시간·"
    "접근 가능한 동선·도착을 보장하지 않습니다. 개인 시간표는 연결하지 않습니다."
)


class TravelInput(ApiModel):
    previous_ends_at: AwareDatetime
    next_starts_at: AwareDatetime
    estimated_travel_minutes: int = Field(strict=True, ge=0, le=1440)

    @field_validator("previous_ends_at", "next_starts_at", mode="before")
    @classmethod
    def explicit_offset(cls, value: object) -> object:
        # Strings only: reject Unix epochs, date-only and implicit local time.
        if not isinstance(value, str) or not re.fullmatch(
            r"20\d{2}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:Z|[+-]\d{2}:\d{2})", value
        ):
            raise ValueError("An explicit offset and whole seconds are required")
        return value

    @model_validator(mode="after")
    def bounded_interval(self) -> "TravelInput":
        if abs((self.next_starts_at - self.previous_ends_at).total_seconds()) > 7 * 86400:
            raise ValueError("The technical calculation window is seven days")
        self.previous_ends_at = self.previous_ends_at.astimezone(UTC)
        self.next_starts_at = self.next_starts_at.astimezone(UTC)
        return self


class TravelResult(ApiModel):
    previous_ends_at: AwareDatetime
    next_starts_at: AwareDatetime
    gap_seconds: int
    travel_seconds: int = Field(ge=0, le=86400)
    remaining_seconds: int
    status: Literal["OVERLAP", "INSUFFICIENT", "NO_MARGIN", "HAS_MARGIN"]
    estimate_source: Literal["USER_INPUT"] = "USER_INPUT"
    calculation_version: Literal["manual-travel-v1"] = "manual-travel-v1"
    notice: Literal[NOTICE] = NOTICE
