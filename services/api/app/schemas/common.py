from datetime import UTC, datetime
from enum import StrEnum

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field


def utc_now() -> datetime:
    return datetime.now(UTC)


class ApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)


class SuccessResponse[T](ApiModel):
    data: T
    resource_version: int | None = Field(default=None, ge=1)
    server_time: AwareDatetime = Field(default_factory=utc_now)


class ErrorCode(StrEnum):
    VALIDATION = "VALIDATION"
    UNAUTHORIZED = "UNAUTHORIZED"
    FORBIDDEN = "FORBIDDEN"
    NOT_FOUND = "NOT_FOUND"
    CONFLICT = "CONFLICT"
    RATE_LIMITED = "RATE_LIMITED"
    UNAVAILABLE = "UNAVAILABLE"
    INTERNAL = "INTERNAL"
    HTTP_ERROR = "HTTP_ERROR"


class ErrorResponse(ApiModel):
    code: ErrorCode
    message: str
    field_errors: dict[str, str] | None = None
    retryable: bool = False
    request_id: str
