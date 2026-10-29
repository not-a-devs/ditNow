from app.core.errors import ApiError
from app.repositories.health import ReadinessProbe
from app.schemas.common import ErrorCode
from app.schemas.health import HealthData


def get_health(probe: ReadinessProbe | None = None) -> HealthData:
    if probe is not None and not probe.is_ready():
        raise ApiError(ErrorCode.UNAVAILABLE)
    return HealthData(status="ok", service="ditnow-api")
