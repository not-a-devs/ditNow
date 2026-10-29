"""FR-OPP-002 personalized discovery routes. Relative paths; root mounts under /api/v1.

Not included in the app router by this task. Defaults fail closed (503) until root injects the
verified principal, the authorized academic-context read and the API-OPP catalog. The optional
recruitment reference seam defaults to NOT_CONNECTED instead of a fake provider.
Every response, including errors, is `private, no-store` because it reflects the actor's context.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.core.errors import ApiError
from app.features.collaboration.router import PrivateNoStoreRoute
from app.features.opportunities.dependencies import (
    Principal,
    auth_not_configured,
    catalog_not_configured,
)
from app.features.opportunities.repository import OpportunityCatalog
from app.features.opportunities.schemas import OpportunityKind
from app.features.opportunity_matching.models import MatchPage, OpportunityBrief
from app.features.opportunity_matching.ports import (
    AcademicContextReader,
    RecruitmentReferenceReader,
)
from app.features.opportunity_matching.service import (
    MAX_PAGE_LIMIT,
    MatchingService,
    normalize_interests,
)
from app.schemas.common import ErrorCode, ErrorResponse, SuccessResponse, utc_now

_ERRORS = {code: {"model": ErrorResponse} for code in (400, 401, 403, 404, 409, 500, 503)}


def academic_context_not_configured() -> AcademicContextReader:
    raise ApiError(ErrorCode.UNAVAILABLE)


def recruitment_not_connected() -> RecruitmentReferenceReader | None:
    return None


@dataclass(frozen=True)
class MatchingDependencies:
    current_principal: Callable[..., Principal] = auth_not_configured
    academic_context: Callable[..., AcademicContextReader] = academic_context_not_configured
    catalog: Callable[..., OpportunityCatalog] = catalog_not_configured
    recruitments: Callable[..., RecruitmentReferenceReader | None] = recruitment_not_connected
    clock: Callable[[], datetime] = utc_now


InterestKinds = Annotated[list[OpportunityKind], Query(alias="interest_kind")]
InterestKeywords = Annotated[list[str], Query(alias="interest_keyword")]


def create_router(deps: MatchingDependencies | None = None) -> APIRouter:
    deps = deps or MatchingDependencies()
    router = APIRouter(
        tags=["opportunity-matching"], responses=_ERRORS, route_class=PrivateNoStoreRoute
    )

    def context(
        principal: Annotated[Principal, Depends(deps.current_principal)],
        contexts: Annotated[AcademicContextReader, Depends(deps.academic_context)],
        catalog: Annotated[OpportunityCatalog, Depends(deps.catalog)],
        recruitments: Annotated[RecruitmentReferenceReader | None, Depends(deps.recruitments)],
    ) -> tuple[Principal, MatchingService]:
        return principal, MatchingService(catalog, contexts, recruitments, clock=deps.clock)

    Context = Annotated[tuple[Principal, MatchingService], Depends(context)]

    @router.get("/me/opportunity-matches", response_model=SuccessResponse[MatchPage])
    def list_matches(
        ctx: Context,
        interest_kinds: InterestKinds = [],  # noqa: B006 - FastAPI copies query defaults
        interest_keywords: InterestKeywords = [],  # noqa: B006
        kind: OpportunityKind | None = None,
        include_closed: bool = False,
        limit: Annotated[int, Query(ge=1, le=MAX_PAGE_LIMIT)] = 10,
        cursor: Annotated[str | None, Query(max_length=40)] = None,
    ) -> SuccessResponse[MatchPage]:
        """Rule-based reference list for the verified actor; not an eligibility decision."""
        principal, service = ctx
        interests = normalize_interests(interest_kinds, interest_keywords)
        page = service.list_matches(
            principal.user_id,
            interests,
            kind=kind,
            include_closed=include_closed,
            limit=limit,
            cursor=cursor,
        )
        return SuccessResponse(data=page)

    @router.get(
        "/me/opportunity-matches/{opportunity_id}/brief",
        response_model=SuccessResponse[OpportunityBrief],
    )
    def get_brief(
        opportunity_id: UUID,
        ctx: Context,
        interest_kinds: InterestKinds = [],  # noqa: B006
        interest_keywords: InterestKeywords = [],  # noqa: B006
    ) -> SuccessResponse[OpportunityBrief]:
        """Original fields, fixed procedure template and evidence; nothing is rewritten."""
        principal, service = ctx
        interests = normalize_interests(interest_kinds, interest_keywords)
        return SuccessResponse(data=service.brief(principal.user_id, opportunity_id, interests))

    return router


# Fail-closed default for root aggregation; replace via create_router(MatchingDependencies(...)).
router = create_router()
