from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.features.discovery.models import DiscoveryPage, Kind
from app.features.discovery.service import DiscoveryService, get_discovery_service
from app.schemas.common import SuccessResponse

router = APIRouter(prefix="/discovery", tags=["public-discovery"])


@router.get("", response_model=SuccessResponse[DiscoveryPage])
def discover(
    q: Annotated[str, Query(min_length=1, max_length=200)],
    service: Annotated[DiscoveryService, Depends(get_discovery_service)],
    kind: Kind = "all",
    offset: Annotated[int, Query(ge=0, le=200)] = 0,
    limit: Annotated[int, Query(ge=1, le=20)] = 10,
) -> SuccessResponse[DiscoveryPage]:
    """Public snapshots only. No personal, authenticated, remote or generated sources."""
    return SuccessResponse(data=service.search(q, kind, offset, limit))
