from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query

from app.features.public_campus.models import Category, PublicGuide, PublicGuidePage, Site
from app.features.public_campus.service import PublicCampusService, get_public_campus_service
from app.schemas.common import SuccessResponse

router = APIRouter(prefix="/public-campus", tags=["public-campus"])
Service = Annotated[PublicCampusService, Depends(get_public_campus_service)]


@router.get("", response_model=SuccessResponse[PublicGuidePage])
def list_guides(
    service: Service,
    q: Annotated[str, Query(max_length=200)] = "",
    category: Category | None = None,
    site: Site | None = None,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
):
    return SuccessResponse(data=service.list_guides(q, category, site, offset, limit))


@router.get("/{record_id}", response_model=SuccessResponse[PublicGuide])
def get_guide(
    record_id: Annotated[str, Path(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$", max_length=80)],
    service: Service,
):
    return SuccessResponse(data=service.get_guide(record_id))
