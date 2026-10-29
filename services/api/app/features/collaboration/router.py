"""Collaboration HTTP routes (not mounted; the root owner includes this router under ``/api/v1``).

Defaults fail closed with 503 ``UNAVAILABLE``: auth and the MariaDB unit of work belong to other
owners. Wire real providers with ``create_collaboration_router(CollaborationDependencies(...))``.
Every response, including errors, carries ``Cache-Control: private, no-store`` because the
payloads are per-caller (``is_mine``, bookmarks, reports, memberships).
"""

import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Path, Query, Request, Response, status
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute
from pydantic import TypeAdapter, ValidationError
from starlette.exceptions import HTTPException

from app.core.errors import (
    ApiError,
    api_error_handler,
    error_response,
    http_error_handler,
    validation_error_handler,
)
from app.core.logging import logger
from app.features.collaboration.domain import PAGE_MAX, CollaborationActor, GroupKind
from app.features.collaboration.idempotency import IDEMPOTENCY_HEADER, KEY_PATTERN
from app.features.collaboration.ports import CollaborationStore
from app.features.collaboration.schemas import (
    ID_PATTERN,
    BookmarkPublic,
    BookmarkState,
    CommentCreate,
    CommentPublic,
    CommentUpdate,
    DeletedResource,
    GroupCreate,
    GroupPublic,
    JoinDecision,
    JoinRequestPublic,
    MembershipLeave,
    MyMembership,
    Page,
    PostSummary,
    ReportCreate,
    ReportPublic,
    SearchText,
    SpacePostCreate,
    SpacePostPublic,
)
from app.features.collaboration.service import CollaborationService, IdFactory, new_id
from app.schemas.common import ErrorCode, ErrorResponse, SuccessResponse, utc_now

ResourceId = Annotated[str, Path(pattern=ID_PATTERN)]
Limit = Annotated[int, Query(ge=1, le=PAGE_MAX)]
Offset = Annotated[int, Query(ge=0, le=10_000)]
RevisionQuery = Annotated[int, Query(ge=1)]
IdempotencyKey = Annotated[str, Header(alias=IDEMPOTENCY_HEADER, pattern=KEY_PATTERN)]
REPLAY_HEADER = "Idempotent-Replayed"
_SEARCH_TEXT = TypeAdapter(SearchText)


class PrivateNoStoreRoute(APIRoute):
    """Applies ``private, no-store`` to success AND error responses of this router."""

    def get_route_handler(self) -> Callable:
        original = super().get_route_handler()

        async def handler(request: Request) -> Response:
            try:
                response = await original(request)
            except ApiError as exc:
                response = await api_error_handler(request, exc)
            except RequestValidationError as exc:
                response = await validation_error_handler(request, exc)
            except HTTPException as exc:
                response = await http_error_handler(request, exc)
            except Exception:
                logger.error(
                    json.dumps(
                        {
                            "event": "collaboration.request.failed",
                            "request_id": request.state.request_id,
                        }
                    )
                )
                response = error_response(ErrorCode.INTERNAL, request.state.request_id)
            response.headers["Cache-Control"] = "private, no-store"
            return response

        return handler


def auth_not_configured() -> CollaborationActor | None:
    raise ApiError(ErrorCode.UNAVAILABLE)


def store_not_configured() -> CollaborationStore:
    raise ApiError(ErrorCode.UNAVAILABLE)


@dataclass(frozen=True)
class CollaborationDependencies:
    """Injected by the auth/DB owners at integration time.

    ``actor`` returns ``None`` for an unauthenticated request (-> 401). It carries identity only;
    participation and group roles are re-read by the store's unit of work in each transaction.
    """

    actor: Callable[..., CollaborationActor | None] = auth_not_configured
    store: Callable[..., CollaborationStore] = store_not_configured
    clock: Callable[[], datetime] = utc_now
    id_factory: IdFactory = new_id


def _search_text(value: str | None, *, required: bool) -> str | None:
    if value is None or (not required and not value.strip()):
        if required:
            raise ApiError(ErrorCode.VALIDATION)
        return None
    try:
        return _SEARCH_TEXT.validate_python(value)
    except ValidationError:
        raise ApiError(ErrorCode.VALIDATION) from None


def create_collaboration_router(deps: CollaborationDependencies | None = None) -> APIRouter:
    deps = deps or CollaborationDependencies()
    router = APIRouter(
        tags=["collaboration"],
        route_class=PrivateNoStoreRoute,
        responses={code: {"model": ErrorResponse} for code in (400, 401, 403, 404, 409, 500, 503)},
    )

    def current_actor(
        actor: Annotated[CollaborationActor | None, Depends(deps.actor)],
    ) -> CollaborationActor:
        if actor is None or not actor.user_id:
            raise ApiError(ErrorCode.UNAUTHORIZED)
        return actor

    Actor = Annotated[CollaborationActor, Depends(current_actor)]

    def collaboration_service(
        _: Actor,  # authentication is decided before the store is ever resolved
        store: Annotated[CollaborationStore, Depends(deps.store)],
    ) -> CollaborationService:
        return CollaborationService(store, clock=deps.clock, id_factory=deps.id_factory)

    Service = Annotated[CollaborationService, Depends(collaboration_service)]

    def replay(response: Response, replayed: bool) -> None:
        if replayed:
            response.headers[REPLAY_HEADER] = "true"

    # ------------------------------------------------------------ FR-COM-002 search/comments

    @router.get("/search/anonymous-posts", response_model=SuccessResponse[Page[PostSummary]])
    def search_anonymous_posts(
        actor: Actor,
        service: Service,
        q: Annotated[str, Query(max_length=200)],
        limit: Limit = 20,
        offset: Offset = 0,
    ):
        text = _search_text(q, required=True)
        return SuccessResponse(
            data=service.search_posts(actor, text or "", limit=limit, offset=offset)
        )

    @router.get(
        "/anonymous-posts/{post_id}/comments",
        response_model=SuccessResponse[Page[CommentPublic]],
    )
    def list_comments(
        actor: Actor, service: Service, post_id: ResourceId, limit: Limit = 20, offset: Offset = 0
    ):
        return SuccessResponse(
            data=service.list_comments(actor, post_id, limit=limit, offset=offset)
        )

    @router.post(
        "/anonymous-posts/{post_id}/comments",
        response_model=SuccessResponse[CommentPublic],
        status_code=status.HTTP_201_CREATED,
    )
    def create_comment(
        actor: Actor,
        service: Service,
        post_id: ResourceId,
        payload: CommentCreate,
        idempotency_key: IdempotencyKey,
        response: Response,
    ):
        comment, replayed = service.create_comment(actor, post_id, payload, idempotency_key)
        replay(response, replayed)
        return SuccessResponse(data=comment, resource_version=comment.revision)

    @router.patch(
        "/anonymous-posts/{post_id}/comments/{comment_id}",
        response_model=SuccessResponse[CommentPublic],
    )
    def update_comment(
        actor: Actor,
        service: Service,
        post_id: ResourceId,
        comment_id: ResourceId,
        payload: CommentUpdate,
    ):
        comment = service.update_comment(actor, post_id, comment_id, payload)
        return SuccessResponse(data=comment, resource_version=comment.revision)

    @router.delete(
        "/anonymous-posts/{post_id}/comments/{comment_id}",
        response_model=SuccessResponse[DeletedResource],
    )
    def delete_comment(
        actor: Actor,
        service: Service,
        post_id: ResourceId,
        comment_id: ResourceId,
        revision: RevisionQuery,
    ):
        deleted = service.delete_comment(actor, post_id, comment_id, revision)
        return SuccessResponse(data=DeletedResource(id=deleted))

    # ------------------------------------------------------------ FR-COM-002 bookmarks

    @router.get("/me/bookmarks", response_model=SuccessResponse[Page[BookmarkPublic]])
    def list_bookmarks(actor: Actor, service: Service, limit: Limit = 20, offset: Offset = 0):
        return SuccessResponse(data=service.list_bookmarks(actor, limit=limit, offset=offset))

    @router.put("/me/bookmarks/{post_id}", response_model=SuccessResponse[BookmarkState])
    def add_bookmark(actor: Actor, service: Service, post_id: ResourceId):
        return SuccessResponse(data=service.add_bookmark(actor, post_id))

    @router.delete("/me/bookmarks/{post_id}", response_model=SuccessResponse[BookmarkState])
    def remove_bookmark(actor: Actor, service: Service, post_id: ResourceId):
        return SuccessResponse(data=service.remove_bookmark(actor, post_id))

    # ------------------------------------------------------------ FR-COM-003 reports

    @router.post(
        "/reports",
        response_model=SuccessResponse[ReportPublic],
        status_code=status.HTTP_201_CREATED,
    )
    def create_report(
        actor: Actor,
        service: Service,
        payload: ReportCreate,
        idempotency_key: IdempotencyKey,
        response: Response,
    ):
        report, replayed = service.create_report(actor, payload, idempotency_key)
        replay(response, replayed)
        return SuccessResponse(data=report)

    @router.get("/me/reports", response_model=SuccessResponse[Page[ReportPublic]])
    def list_my_reports(actor: Actor, service: Service, limit: Limit = 20, offset: Offset = 0):
        return SuccessResponse(data=service.list_my_reports(actor, limit=limit, offset=offset))

    # ------------------------------------------------------------ FR-COM-006 groups

    @router.get("/groups", response_model=SuccessResponse[Page[GroupPublic]])
    def list_groups(
        actor: Actor,
        service: Service,
        kind: GroupKind | None = None,
        q: Annotated[str | None, Query(max_length=200)] = None,
        limit: Limit = 20,
        offset: Offset = 0,
    ):
        text = _search_text(q, required=False)
        return SuccessResponse(
            data=service.list_groups(actor, kind=kind, text=text, limit=limit, offset=offset)
        )

    @router.post(
        "/groups",
        response_model=SuccessResponse[GroupPublic],
        status_code=status.HTTP_201_CREATED,
    )
    def create_group(
        actor: Actor,
        service: Service,
        payload: GroupCreate,
        idempotency_key: IdempotencyKey,
        response: Response,
    ):
        group, replayed = service.create_group(actor, payload, idempotency_key)
        replay(response, replayed)
        return SuccessResponse(data=group, resource_version=group.revision)

    @router.get("/groups/{group_id}", response_model=SuccessResponse[GroupPublic])
    def get_group(actor: Actor, service: Service, group_id: ResourceId):
        group = service.get_group(actor, group_id)
        return SuccessResponse(data=group, resource_version=group.revision)

    @router.post(
        "/groups/{group_id}/join-requests",
        response_model=SuccessResponse[MyMembership],
        status_code=status.HTTP_201_CREATED,
    )
    def request_join(
        actor: Actor,
        service: Service,
        group_id: ResourceId,
        idempotency_key: IdempotencyKey,
        response: Response,
    ):
        membership, replayed = service.request_join(actor, group_id, idempotency_key)
        replay(response, replayed)
        return SuccessResponse(data=membership, resource_version=membership.revision)

    @router.get(
        "/groups/{group_id}/join-requests",
        response_model=SuccessResponse[Page[JoinRequestPublic]],
    )
    def list_join_requests(
        actor: Actor, service: Service, group_id: ResourceId, limit: Limit = 20, offset: Offset = 0
    ):
        return SuccessResponse(
            data=service.list_join_requests(actor, group_id, limit=limit, offset=offset)
        )

    @router.post(
        "/groups/{group_id}/join-requests/{membership_id}/decision",
        response_model=SuccessResponse[JoinRequestPublic],
    )
    def decide_join(
        actor: Actor,
        service: Service,
        group_id: ResourceId,
        membership_id: ResourceId,
        payload: JoinDecision,
    ):
        decided = service.decide_join(actor, group_id, membership_id, payload)
        return SuccessResponse(data=decided, resource_version=decided.revision)

    @router.post(
        "/groups/{group_id}/membership/leave", response_model=SuccessResponse[MyMembership]
    )
    def leave_group(actor: Actor, service: Service, group_id: ResourceId, payload: MembershipLeave):
        membership = service.leave_group(actor, group_id, payload)
        return SuccessResponse(data=membership, resource_version=membership.revision)

    # ------------------------------------------------------------ FR-COM-007 team space

    @router.get(
        "/groups/{group_id}/space/posts",
        response_model=SuccessResponse[Page[SpacePostPublic]],
    )
    def list_space_posts(
        actor: Actor, service: Service, group_id: ResourceId, limit: Limit = 20, offset: Offset = 0
    ):
        return SuccessResponse(
            data=service.list_space_posts(actor, group_id, limit=limit, offset=offset)
        )

    @router.post(
        "/groups/{group_id}/space/posts",
        response_model=SuccessResponse[SpacePostPublic],
        status_code=status.HTTP_201_CREATED,
    )
    def create_space_post(
        actor: Actor,
        service: Service,
        group_id: ResourceId,
        payload: SpacePostCreate,
        idempotency_key: IdempotencyKey,
        response: Response,
    ):
        post, replayed = service.create_space_post(actor, group_id, payload, idempotency_key)
        replay(response, replayed)
        return SuccessResponse(data=post, resource_version=post.revision)

    @router.delete(
        "/groups/{group_id}/space/posts/{post_id}",
        response_model=SuccessResponse[DeletedResource],
    )
    def delete_space_post(
        actor: Actor,
        service: Service,
        group_id: ResourceId,
        post_id: ResourceId,
        revision: RevisionQuery,
    ):
        deleted = service.delete_space_post(actor, group_id, post_id, revision)
        return SuccessResponse(data=DeletedResource(id=deleted))

    return router


router = create_collaboration_router()
