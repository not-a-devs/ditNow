"""Thin async transport over existing DTOs/parsers/domain services and P0Executor UOWs."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Response

from app.features.community.router import IdempotencyKey, Limit, Offset, ResourceId
from app.features.community.schemas import (
    AnonymousPostCreate,
    AnonymousPostPage,
    AnonymousPostPublic,
    AnonymousPostUpdate,
    DeletedResource,
    RecruitmentClose,
    RecruitmentCreate,
    RecruitmentPage,
    RecruitmentPublic,
    RecruitmentUpdate,
)
from app.features.opportunities.repository import OpportunityQuery
from app.features.opportunities.router import IdempotencyKey as CheckKey
from app.features.opportunities.router import IfMatch, parse_if_match
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
from app.integrations.platform_runtime.dependencies import Context, Runtime
from app.schemas.common import ErrorResponse, SuccessResponse

router = APIRouter(
    tags=["p0-live"],
    responses={code: {"model": ErrorResponse} for code in (400, 401, 403, 404, 409, 429, 500, 503)},
)


@router.get("/anonymous-posts", response_model=SuccessResponse[AnonymousPostPage])
async def list_posts(ctx: Context, limit: Limit = 20, offset: Offset = 0):
    return SuccessResponse(
        data=await ctx.runtime.run(
            ctx.token,
            ctx.binding.principal,
            lambda s: s.posts.list(s.actor, limit=limit, offset=offset),
        )
    )


@router.get("/anonymous-posts/{post_id}", response_model=SuccessResponse[AnonymousPostPublic])
async def get_post(post_id: ResourceId, ctx: Context):
    post = await ctx.runtime.run(
        ctx.token, ctx.binding.principal, lambda s: s.posts.get(s.actor, post_id)
    )
    return SuccessResponse(data=post, resource_version=post.revision)


@router.post(
    "/anonymous-posts", response_model=SuccessResponse[AnonymousPostPublic], status_code=201
)
async def create_post(
    body: AnonymousPostCreate, idempotency_key: IdempotencyKey, response: Response, ctx: Context
):
    post, replay = await ctx.runtime.run(
        ctx.token, ctx.binding.principal, lambda s: s.posts.create(s.actor, body, idempotency_key)
    )
    if replay:
        response.headers["Idempotent-Replayed"] = "true"
    return SuccessResponse(data=post, resource_version=post.revision)


@router.patch("/anonymous-posts/{post_id}", response_model=SuccessResponse[AnonymousPostPublic])
async def patch_post(post_id: ResourceId, body: AnonymousPostUpdate, ctx: Context):
    post = await ctx.runtime.run(
        ctx.token, ctx.binding.principal, lambda s: s.posts.update(s.actor, post_id, body)
    )
    return SuccessResponse(data=post, resource_version=post.revision)


@router.delete("/anonymous-posts/{post_id}", response_model=SuccessResponse[DeletedResource])
async def delete_post(post_id: ResourceId, ctx: Context, revision: Annotated[int, Query(ge=1)]):
    id = await ctx.runtime.run(
        ctx.token, ctx.binding.principal, lambda s: s.posts.delete(s.actor, post_id, revision)
    )
    return SuccessResponse(data=DeletedResource(id=id))


@router.get("/recruitments", response_model=SuccessResponse[RecruitmentPage])
async def list_recruitments(ctx: Context, limit: Limit = 20, offset: Offset = 0):
    return SuccessResponse(
        data=await ctx.runtime.run(
            ctx.token,
            ctx.binding.principal,
            lambda s: s.recruitments.list(s.actor, limit=limit, offset=offset),
        )
    )


@router.get("/recruitments/{recruitment_id}", response_model=SuccessResponse[RecruitmentPublic])
async def get_recruitment(recruitment_id: ResourceId, ctx: Context):
    row = await ctx.runtime.run(
        ctx.token, ctx.binding.principal, lambda s: s.recruitments.get(s.actor, recruitment_id)
    )
    return SuccessResponse(data=row, resource_version=row.revision)


@router.post("/recruitments", response_model=SuccessResponse[RecruitmentPublic], status_code=201)
async def create_recruitment(
    body: RecruitmentCreate, idempotency_key: IdempotencyKey, response: Response, ctx: Context
):
    row, replay = await ctx.runtime.run(
        ctx.token,
        ctx.binding.principal,
        lambda s: s.recruitments.create(s.actor, body, idempotency_key),
    )
    if replay:
        response.headers["Idempotent-Replayed"] = "true"
    return SuccessResponse(data=row, resource_version=row.revision)


@router.patch("/recruitments/{recruitment_id}", response_model=SuccessResponse[RecruitmentPublic])
async def patch_recruitment(recruitment_id: ResourceId, body: RecruitmentUpdate, ctx: Context):
    row = await ctx.runtime.run(
        ctx.token,
        ctx.binding.principal,
        lambda s: s.recruitments.update(s.actor, recruitment_id, body),
    )
    return SuccessResponse(data=row, resource_version=row.revision)


@router.post(
    "/recruitments/{recruitment_id}/close", response_model=SuccessResponse[RecruitmentPublic]
)
async def close_recruitment(recruitment_id: ResourceId, body: RecruitmentClose, ctx: Context):
    row = await ctx.runtime.run(
        ctx.token,
        ctx.binding.principal,
        lambda s: s.recruitments.close(s.actor, recruitment_id, body),
    )
    return SuccessResponse(data=row, resource_version=row.revision)


@router.delete("/recruitments/{recruitment_id}", response_model=SuccessResponse[DeletedResource])
async def delete_recruitment(
    recruitment_id: ResourceId, ctx: Context, revision: Annotated[int, Query(ge=1)]
):
    row = await ctx.runtime.run(
        ctx.token,
        ctx.binding.principal,
        lambda s: s.recruitments.cancel(
            s.actor, recruitment_id, RecruitmentClose(revision=revision)
        ),
    )
    return SuccessResponse(data=DeletedResource(id=row.id))


@router.get("/opportunities", response_model=SuccessResponse[OpportunityPageData])
async def list_opportunities(
    runtime: Runtime,
    kind: OpportunityKind | None = None,
    q: Annotated[str | None, Query(min_length=1, max_length=50)] = None,
    department: Annotated[
        str | None, Query(min_length=1, max_length=20, pattern=r"^[A-Za-z0-9_-]+$")
    ] = None,
    open_only: bool = False,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
    cursor: Annotated[str | None, Query(max_length=200)] = None,
):
    query = OpportunityQuery(
        kind=kind,
        text=q.strip() if q and q.strip() else None,
        department_code=department,
        open_only=open_only,
        limit=limit,
        cursor=cursor,
    )
    return SuccessResponse(data=await runtime.public(lambda service: service.list_public(query)))


@router.get(
    "/opportunities/{opportunity_id}", response_model=SuccessResponse[OpportunityDetailData]
)
async def get_opportunity(opportunity_id: UUID, runtime: Runtime):
    return SuccessResponse(
        data=await runtime.public(lambda service: service.get_public(opportunity_id))
    )


@router.get("/me/saved-opportunities", response_model=SuccessResponse[SavedOpportunityListData])
async def list_saved(ctx: Context):
    rows = await ctx.runtime.personal(
        ctx.token,
        ctx.binding.principal,
        lambda service: service.list_saved(ctx.binding.principal.user_id),
    )
    return SuccessResponse(data=SavedOpportunityListData(items=rows))


@router.put(
    "/me/saved-opportunities/{opportunity_id}", response_model=SuccessResponse[SavedOpportunityData]
)
async def save_opportunity(
    opportunity_id: UUID,
    response: Response,
    ctx: Context,
    body: SaveOpportunityRequest | None = None,
):
    row, created = await ctx.runtime.personal(
        ctx.token,
        ctx.binding.principal,
        lambda service: service.save(
            ctx.binding.principal.user_id, opportunity_id, body or SaveOpportunityRequest()
        ),
    )
    response.status_code = 201 if created else 200
    return SuccessResponse(data=row, resource_version=row.revision)


@router.patch(
    "/me/saved-opportunities/{opportunity_id}", response_model=SuccessResponse[SavedOpportunityData]
)
async def patch_saved(
    opportunity_id: UUID, body: SavedOpportunityPatch, if_match: IfMatch, ctx: Context
):
    revision = parse_if_match(if_match)
    row = await ctx.runtime.personal(
        ctx.token,
        ctx.binding.principal,
        lambda service: service.update(
            ctx.binding.principal.user_id, opportunity_id, body, revision
        ),
    )
    return SuccessResponse(data=row, resource_version=row.revision)


@router.delete(
    "/me/saved-opportunities/{opportunity_id}", response_model=SuccessResponse[DeletedData]
)
async def delete_saved(opportunity_id: UUID, if_match: IfMatch, ctx: Context):
    revision = parse_if_match(if_match)
    await ctx.runtime.personal(
        ctx.token,
        ctx.binding.principal,
        lambda service: service.delete(ctx.binding.principal.user_id, opportunity_id, revision),
    )
    return SuccessResponse(data=DeletedData(deleted=True))


@router.post(
    "/me/saved-opportunities/{opportunity_id}/checks", response_model=SuccessResponse[CheckItemData]
)
async def add_check(
    opportunity_id: UUID,
    body: CheckItemCreate,
    idempotency_key: CheckKey,
    response: Response,
    ctx: Context,
):
    row, created = await ctx.runtime.personal(
        ctx.token,
        ctx.binding.principal,
        lambda service: service.add_check(
            ctx.binding.principal.user_id, opportunity_id, body, idempotency_key
        ),
    )
    response.status_code = 201 if created else 200
    return SuccessResponse(data=row, resource_version=row.revision)


@router.patch(
    "/me/saved-opportunities/{opportunity_id}/checks/{check_id}",
    response_model=SuccessResponse[CheckItemData],
)
async def patch_check(
    opportunity_id: UUID, check_id: UUID, body: CheckItemPatch, if_match: IfMatch, ctx: Context
):
    revision = parse_if_match(if_match)
    row = await ctx.runtime.personal(
        ctx.token,
        ctx.binding.principal,
        lambda service: service.update_check(
            ctx.binding.principal.user_id, opportunity_id, check_id, body, revision
        ),
    )
    return SuccessResponse(data=row, resource_version=row.revision)


@router.delete(
    "/me/saved-opportunities/{opportunity_id}/checks/{check_id}",
    response_model=SuccessResponse[DeletedData],
)
async def delete_check(opportunity_id: UUID, check_id: UUID, if_match: IfMatch, ctx: Context):
    revision = parse_if_match(if_match)
    await ctx.runtime.personal(
        ctx.token,
        ctx.binding.principal,
        lambda service: service.delete_check(
            ctx.binding.principal.user_id, opportunity_id, check_id, revision
        ),
    )
    return SuccessResponse(data=DeletedData(deleted=True))
