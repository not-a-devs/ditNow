"""Community HTTP routes (not mounted; the root owner includes this router under ``/api/v1``).

Every route requires a server-verified actor. Auth and DB are owned by other branches, so the
default dependencies fail closed with 503 ``UNAVAILABLE`` instead of serving unauthenticated or
non-persistent data. Wire real providers with
``create_community_router(CommunityDependencies(...))``.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Path, Query, Response, status

from app.core.errors import ApiError
from app.features.community.domain import PAGE_MAX, CommunityActor, require_member
from app.features.community.idempotency import IDEMPOTENCY_HEADER, KEY_PATTERN
from app.features.community.repository import (
    AnonymousPostRepository,
    OpportunityVisibility,
    PublicProfileReader,
    RecruitmentRepository,
)
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
from app.features.community.service import (
    AnonymousPostService,
    IdFactory,
    RecruitmentService,
    new_id,
)
from app.schemas.common import ErrorCode, ErrorResponse, SuccessResponse, utc_now

ResourceId = Annotated[str, Path(pattern=r"^[A-Za-z0-9_-]{1,64}$")]
Limit = Annotated[int, Query(ge=1, le=PAGE_MAX)]
Offset = Annotated[int, Query(ge=0, le=10_000)]
# Required on create POSTs: there is no natural unique key, so a retry must not duplicate.
IdempotencyKey = Annotated[str, Header(alias=IDEMPOTENCY_HEADER, pattern=KEY_PATTERN)]

_ERRORS = {code: {"model": ErrorResponse} for code in (400, 401, 403, 404, 409, 500, 503)}
REPLAY_HEADER = "Idempotent-Replayed"


def auth_not_configured() -> CommunityActor | None:
    raise ApiError(ErrorCode.UNAVAILABLE)


def storage_not_configured() -> object:
    raise ApiError(ErrorCode.UNAVAILABLE)


def opportunities_not_configured() -> OpportunityVisibility | None:
    # Unlike auth/storage this does not fail the whole request: recruitments without an
    # opportunity link still work, and any requested link is refused by the service.
    return None


def private_no_store(response: Response) -> None:
    # Responses carry per-caller ``is_mine``; shared/browser caches must never reuse them.
    response.headers["Cache-Control"] = "private, no-store"


@dataclass(frozen=True)
class CommunityDependencies:
    """FastAPI dependency callables supplied by the auth/DB owners at integration time.

    ``actor`` returns ``None`` for an unauthenticated request (-> 401) and must derive
    ``community_access`` from server-side role data. Repositories must be real persistence.
    """

    actor: Callable[..., CommunityActor | None] = auth_not_configured
    posts: Callable[..., AnonymousPostRepository] = storage_not_configured
    recruitments: Callable[..., RecruitmentRepository] = storage_not_configured
    profiles: Callable[..., PublicProfileReader] = storage_not_configured
    opportunities: Callable[..., OpportunityVisibility | None] = opportunities_not_configured
    clock: Callable[[], datetime] = utc_now
    id_factory: IdFactory = new_id


def create_community_router(deps: CommunityDependencies | None = None) -> APIRouter:
    deps = deps or CommunityDependencies()
    router = APIRouter(
        tags=["community"], responses=_ERRORS, dependencies=[Depends(private_no_store)]
    )

    def current_member(
        actor: Annotated[CommunityActor | None, Depends(deps.actor)],
    ) -> CommunityActor:
        # Resolved before storage dependencies so unauthenticated calls never touch the DB.
        return require_member(actor)

    Actor = Annotated[CommunityActor, Depends(current_member)]

    def post_service(
        posts: Annotated[AnonymousPostRepository, Depends(deps.posts)],
    ) -> AnonymousPostService:
        return AnonymousPostService(posts, clock=deps.clock, id_factory=deps.id_factory)

    def recruitment_service(
        recruitments: Annotated[RecruitmentRepository, Depends(deps.recruitments)],
        profiles: Annotated[PublicProfileReader, Depends(deps.profiles)],
        opportunities: Annotated[OpportunityVisibility | None, Depends(deps.opportunities)],
    ) -> RecruitmentService:
        return RecruitmentService(
            recruitments,
            profiles,
            opportunities=opportunities,
            clock=deps.clock,
            id_factory=deps.id_factory,
        )

    def created(response: Response, replayed: bool) -> None:
        if replayed:
            response.headers[REPLAY_HEADER] = "true"

    Posts = Annotated[AnonymousPostService, Depends(post_service)]
    Recruitments = Annotated[RecruitmentService, Depends(recruitment_service)]

    # ------------------------------------------------------------ FR-COM-001 anonymous posts

    @router.get("/anonymous-posts", response_model=SuccessResponse[AnonymousPostPage])
    def list_anonymous_posts(actor: Actor, service: Posts, limit: Limit = 20, offset: Offset = 0):
        return SuccessResponse(data=service.list(actor, limit=limit, offset=offset))

    @router.get("/anonymous-posts/{post_id}", response_model=SuccessResponse[AnonymousPostPublic])
    def get_anonymous_post(actor: Actor, service: Posts, post_id: ResourceId):
        post = service.get(actor, post_id)
        return SuccessResponse(data=post, resource_version=post.revision)

    @router.post(
        "/anonymous-posts",
        response_model=SuccessResponse[AnonymousPostPublic],
        status_code=status.HTTP_201_CREATED,
    )
    def create_anonymous_post(
        actor: Actor,
        service: Posts,
        payload: AnonymousPostCreate,
        idempotency_key: IdempotencyKey,
        response: Response,
    ):
        post, replayed = service.create(actor, payload, idempotency_key)
        created(response, replayed)
        return SuccessResponse(data=post, resource_version=post.revision)

    @router.patch("/anonymous-posts/{post_id}", response_model=SuccessResponse[AnonymousPostPublic])
    def update_anonymous_post(
        actor: Actor, service: Posts, post_id: ResourceId, payload: AnonymousPostUpdate
    ):
        post = service.update(actor, post_id, payload)
        return SuccessResponse(data=post, resource_version=post.revision)

    @router.delete("/anonymous-posts/{post_id}", response_model=SuccessResponse[DeletedResource])
    def delete_anonymous_post(
        actor: Actor,
        service: Posts,
        post_id: ResourceId,
        revision: Annotated[int, Query(ge=1)],
    ):
        return SuccessResponse(data=DeletedResource(id=service.delete(actor, post_id, revision)))

    # ------------------------------------------------------------ FR-COM-004 recruitments

    @router.get("/recruitments", response_model=SuccessResponse[RecruitmentPage])
    def list_recruitments(
        actor: Actor, service: Recruitments, limit: Limit = 20, offset: Offset = 0
    ):
        return SuccessResponse(data=service.list(actor, limit=limit, offset=offset))

    @router.get("/recruitments/{recruitment_id}", response_model=SuccessResponse[RecruitmentPublic])
    def get_recruitment(actor: Actor, service: Recruitments, recruitment_id: ResourceId):
        item = service.get(actor, recruitment_id)
        return SuccessResponse(data=item, resource_version=item.revision)

    @router.post(
        "/recruitments",
        response_model=SuccessResponse[RecruitmentPublic],
        status_code=status.HTTP_201_CREATED,
    )
    def create_recruitment(
        actor: Actor,
        service: Recruitments,
        payload: RecruitmentCreate,
        idempotency_key: IdempotencyKey,
        response: Response,
    ):
        item, replayed = service.create(actor, payload, idempotency_key)
        created(response, replayed)
        return SuccessResponse(data=item, resource_version=item.revision)

    @router.patch(
        "/recruitments/{recruitment_id}", response_model=SuccessResponse[RecruitmentPublic]
    )
    def update_recruitment(
        actor: Actor, service: Recruitments, recruitment_id: ResourceId, payload: RecruitmentUpdate
    ):
        item = service.update(actor, recruitment_id, payload)
        return SuccessResponse(data=item, resource_version=item.revision)

    @router.post(
        "/recruitments/{recruitment_id}/close", response_model=SuccessResponse[RecruitmentPublic]
    )
    def close_recruitment(
        actor: Actor, service: Recruitments, recruitment_id: ResourceId, payload: RecruitmentClose
    ):
        item = service.close(actor, recruitment_id, payload)
        return SuccessResponse(data=item, resource_version=item.revision)

    return router


router = create_community_router()
