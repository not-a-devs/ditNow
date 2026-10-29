from typing import Literal
from uuid import UUID

from pydantic import Field

from app.schemas.common import ApiModel


class SessionProfile(ApiModel):
    """Own-account projection; never reuse this model in anonymous post responses."""

    user_id: UUID
    display_name: str = Field(min_length=1, max_length=100)
    record_source: Literal["DEMO"] = "DEMO"
    department_id: UUID
    department_code: str = Field(min_length=1, max_length=50)
    academic_year: int = Field(ge=1)
    community_access: bool
