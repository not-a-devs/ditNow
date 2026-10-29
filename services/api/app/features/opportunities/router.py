"""API-OPP routes. Paths are relative; root mounts this router under /api/v1.

Not included in the app router by this task. `router` uses fail-closed defaults (503).
"""

import re
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Response

from app.core.errors import ApiError
from app.features.opportunities.dependencies import OpportunityDependencies, Principal
from app.features.opportunities.repository import (
    OpportunityCatalog,
    OpportunityQuery,
    SavedOpportunityStore,
)
from app.features.opportunities.schemas import (
    CheckItemCreate,
    CheckItemData,
    CheckItemPatch,
    DeletedData,
    OpportunityDetailData,
    OpportunityKind,
    OpportunityPageData,
    SavedOpportunityData,
    SavedOpportunityListData,
    SavedOpportunityPatch,
    SaveOpportunityRequest,
)
from app.features.opportunities.service import OpportunityService
from app.schemas.common import ErrorCode, ErrorResponse, SuccessResponse

_ERRORS = {code: {"model": ErrorResponse} for code in (400, 401, 403, 404, 409, 500, 503)}


# RFC 9110 If-Match uses the strong comparison. Accept exactly one revision, either bare or as a
# strong entity-tag: `7` or `"7"`. Weak tags (W/), lists, `*`, unbalanced quotes, leading zeros
# and non-ASCII digits are rejected (400). `[0-9]` is ASCII-only in Python `re`.
_IF_MATCH = re.compile(r'(?:"(?P<quoted>[1-9][0-9]{0,8})"|(?P<bare>[1-9][0-9]{0,8}))')


def parse_if_match(value: str) -> int:
    match = _IF_MATCH.fullmatch(value.strip(" 	"))
    if match is None:
        raise ApiError(ErrorCode.VALIDATION)
    return int(match["quoted"] or match["bare"])


IfMatch = Annotated[str, Header(alias="If-Match", max_length=16)]
IdempotencyKey = Annotated[
    str, Header(alias="Idempotency-Key", min_length=8, max_length=100, pattern=r"^[A-Za-z0-9_-]+$")
]


def create_router(deps: OpportunityDependencies | None = None) -> APIRouter:
    deps = deps or OpportunityDependencies()
    router = APIRouter(tags=["opportunities"], responses=_ERRORS)

    def public_service(
        catalog: Annotated[OpportunityCatalog, Depends(deps.catalog)],
    ) -> OpportunityService:
        return OpportunityService(catalog)

    def owner_context(
        principal: Annotated[Principal, Depends(deps.current_principal)],
        catalog: Annotated[OpportunityCatalog, Depends(deps.catalog)],
        store: Annotated[SavedOpportunityStore, Depends(deps.store)],
    ) -> tuple[Principal, OpportunityService]:
        return principal, OpportunityService(catalog, store)

    Public = Annotated[OpportunityService, Depends(public_service)]
    Owner = Annotated[tuple[Principal, OpportunityService], Depends(owner_context)]

    @router.get("/opportunities", response_model=SuccessResponse[OpportunityPageData])
    def list_opportunities(
        service: Public,
        kind: OpportunityKind | None = None,
        q: Annotated[str | None, Query(min_length=1, max_length=50)] = None,
        department: Annotated[
            str | None, Query(min_length=1, max_length=20, pattern=r"^[A-Za-z0-9_-]+$")
        ] = None,
        open_only: bool = False,
        limit: Annotated[int, Query(ge=1, le=50)] = 20,
        cursor: Annotated[str | None, Query(max_length=200)] = None,
    ) -> SuccessResponse[OpportunityPageData]:
        """Public approved projection only. `department` narrows display; not authorization."""
        query = OpportunityQuery(
            kind=kind,
            text=q.strip() if q and q.strip() else None,
            department_code=department,
            open_only=open_only,
            limit=limit,
            cursor=cursor,
        )
        return SuccessResponse(data=service.list_public(query))

    @router.get(
        "/opportunities/{opportunity_id}", response_model=SuccessResponse[OpportunityDetailData]
    )
    def get_opportunity(
        opportunity_id: UUID, service: Public
    ) -> SuccessResponse[OpportunityDetailData]:
        return SuccessResponse(data=service.get_public(opportunity_id))

    @router.get("/me/saved-opportunities", response_model=SuccessResponse[SavedOpportunityListData])
    def list_saved(owner: Owner) -> SuccessResponse[SavedOpportunityListData]:
        principal, service = owner
        return SuccessResponse(
            data=SavedOpportunityListData(items=service.list_saved(principal.user_id))
        )

    @router.put(
        "/me/saved-opportunities/{opportunity_id}",
        response_model=SuccessResponse[SavedOpportunityData],
    )
    def save_opportunity(
        opportunity_id: UUID,
        response: Response,
        owner: Owner,
        body: SaveOpportunityRequest | None = None,
    ) -> SuccessResponse[SavedOpportunityData]:
        principal, service = owner
        saved, created = service.save(
            principal.user_id, opportunity_id, body or SaveOpportunityRequest()
        )
        response.status_code = 201 if created else 200
        return SuccessResponse(data=saved, resource_version=saved.revision)

    @router.patch(
        "/me/saved-opportunities/{opportunity_id}",
        response_model=SuccessResponse[SavedOpportunityData],
    )
    def update_saved(
        opportunity_id: UUID,
        body: SavedOpportunityPatch,
        if_match: IfMatch,
        owner: Owner,
    ) -> SuccessResponse[SavedOpportunityData]:
        principal, service = owner
        saved = service.update(principal.user_id, opportunity_id, body, parse_if_match(if_match))
        return SuccessResponse(data=saved, resource_version=saved.revision)

    @router.delete(
        "/me/saved-opportunities/{opportunity_id}", response_model=SuccessResponse[DeletedData]
    )
    def delete_saved(
        opportunity_id: UUID, if_match: IfMatch, owner: Owner
    ) -> SuccessResponse[DeletedData]:
        principal, service = owner
        service.delete(principal.user_id, opportunity_id, parse_if_match(if_match))
        return SuccessResponse(data=DeletedData(deleted=True))

    @router.post(
        "/me/saved-opportunities/{opportunity_id}/checks",
        response_model=SuccessResponse[CheckItemData],
    )
    def add_check(
        opportunity_id: UUID,
        body: CheckItemCreate,
        idempotency_key: IdempotencyKey,
        response: Response,
        owner: Owner,
    ) -> SuccessResponse[CheckItemData]:
        principal, service = owner
        check, created = service.add_check(principal.user_id, opportunity_id, body, idempotency_key)
        response.status_code = 201 if created else 200
        return SuccessResponse(data=check, resource_version=check.revision)

    @router.patch(
        "/me/saved-opportunities/{opportunity_id}/checks/{check_id}",
        response_model=SuccessResponse[CheckItemData],
    )
    def update_check(
        opportunity_id: UUID,
        check_id: UUID,
        body: CheckItemPatch,
        if_match: IfMatch,
        owner: Owner,
    ) -> SuccessResponse[CheckItemData]:
        principal, service = owner
        check = service.update_check(
            principal.user_id, opportunity_id, check_id, body, parse_if_match(if_match)
        )
        return SuccessResponse(data=check, resource_version=check.revision)

    @router.delete(
        "/me/saved-opportunities/{opportunity_id}/checks/{check_id}",
        response_model=SuccessResponse[DeletedData],
    )
    def delete_check(
        opportunity_id: UUID, check_id: UUID, if_match: IfMatch, owner: Owner
    ) -> SuccessResponse[DeletedData]:
        principal, service = owner
        service.delete_check(principal.user_id, opportunity_id, check_id, parse_if_match(if_match))
        return SuccessResponse(data=DeletedData(deleted=True))

    return router


# Fail-closed default for root aggregation; replace via create_router(OpportunityDependencies(...)).
router = create_router()
