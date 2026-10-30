"""Public read-only provenance explanation routes (not mounted; the root owner includes this router
under ``/api/v1``).

No actor, department or role is read: the content is identical for every caller and grants no
privileges. Any query parameter is rejected so the endpoint can never accept arbitrary URLs.
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Request

from app.core.errors import ApiError
from app.features.collaboration.router import PrivateNoStoreRoute
from app.features.data_provenance.schemas import (
    ProvenanceLabel,
    ProvenanceLabelInfo,
    ProvenanceOverview,
)
from app.features.data_provenance.service import ProvenanceCatalog, fixed_catalog
from app.schemas.common import ErrorCode, ErrorResponse, SuccessResponse


@dataclass(frozen=True)
class DataProvenanceDependencies:
    catalog: Callable[..., ProvenanceCatalog] = fixed_catalog


def reject_query(request: Request) -> None:
    if request.query_params:
        raise ApiError(ErrorCode.VALIDATION)


def create_data_provenance_router(deps: DataProvenanceDependencies | None = None) -> APIRouter:
    deps = deps or DataProvenanceDependencies()
    router = APIRouter(
        prefix="/data-provenance",
        tags=["data-provenance"],
        route_class=PrivateNoStoreRoute,
        dependencies=[Depends(reject_query)],
        responses={code: {"model": ErrorResponse} for code in (400, 404, 500, 503)},
    )

    Catalog = Annotated[ProvenanceCatalog, Depends(deps.catalog)]

    @router.get("", response_model=SuccessResponse[ProvenanceOverview])
    def get_provenance_overview(catalog: Catalog):
        return SuccessResponse(data=catalog.overview())

    @router.get("/labels/{label}", response_model=SuccessResponse[ProvenanceLabelInfo])
    def get_provenance_label(catalog: Catalog, label: Annotated[ProvenanceLabel, Path()]):
        return SuccessResponse(data=catalog.label(label))

    return router


router = create_data_provenance_router()
