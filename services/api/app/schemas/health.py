from typing import Literal

from app.schemas.common import ApiModel


class HealthData(ApiModel):
    status: Literal["ok"]
    service: Literal["ditnow-api"]
