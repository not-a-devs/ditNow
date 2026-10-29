import json
from collections.abc import Callable
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute
from starlette.exceptions import HTTPException

from app.core.errors import (
    ApiError,
    api_error_handler,
    error_response,
    http_error_handler,
    validation_error_handler,
)
from app.core.logging import logger
from app.features.notice_discussion.models import (
    CommentUpdate,
    Content,
    ItemView,
    NoticeSummary,
    NoticeView,
    Page,
    QuestionInput,
    QuestionUpdate,
)
from app.features.notice_discussion.service import KEY_PATTERN, NoticeDiscussionService
from app.schemas.common import ErrorCode, SuccessResponse


class PrivateRoute(APIRoute):
    def get_route_handler(self) -> Callable:
        original = super().get_route_handler()

        async def handle(request: Request) -> Response:
            try:
                response = await original(request)
            except ApiError as error:
                response = await api_error_handler(request, error)
            except RequestValidationError as error:
                response = await validation_error_handler(request, error)
            except HTTPException as error:
                response = await http_error_handler(request, error)
            except Exception:
                logger.error(
                    json.dumps(
                        {
                            "event": "notice_discussion.request.failed",
                            "request_id": request.state.request_id,
                        }
                    )
                )
                response = error_response(ErrorCode.INTERNAL, request.state.request_id)
            response.headers["Cache-Control"] = "private, no-store"
            return response

        return handle


def get_actor() -> UUID:
    """Only the approved common identity bridge can supply this; no header/fake identity."""
    raise ApiError(ErrorCode.UNAVAILABLE)


def get_service() -> NoticeDiscussionService:
    raise ApiError(ErrorCode.UNAVAILABLE)


Actor = Annotated[UUID, Depends(get_actor)]
Service = Annotated[NoticeDiscussionService, Depends(get_service)]
Key = Annotated[str, Header(alias="Idempotency-Key", pattern=KEY_PATTERN)]
Offset = Annotated[int, Query(ge=0)]
Limit = Annotated[int, Query(ge=1, le=50)]
router = APIRouter(
    prefix="/notice-discussion", tags=["notice-discussion-first-pass"], route_class=PrivateRoute
)


@router.get("/notices", response_model=SuccessResponse[list[NoticeSummary]])
def notices(
    actor: Actor, service: Service, q: Annotated[str, Query(max_length=100)] = "", limit: Limit = 25
):
    return SuccessResponse(data=service.notices(actor, q, limit))


@router.get("/notices/{notice_id}", response_model=SuccessResponse[NoticeView])
def notice(notice_id: UUID, actor: Actor, service: Service):
    return SuccessResponse(data=service.notice(actor, notice_id))


@router.get(
    "/departments/{department_id}/questions", response_model=SuccessResponse[Page[ItemView]]
)
def questions(
    department_id: UUID, actor: Actor, service: Service, offset: Offset = 0, limit: Limit = 25
):
    return SuccessResponse(data=service.items(actor, department_id, offset=offset, limit=limit))


@router.post("/departments/{department_id}/questions", response_model=SuccessResponse[ItemView])
def create_question(
    department_id: UUID, body: QuestionInput, key: Key, actor: Actor, service: Service
):
    return SuccessResponse(data=service.create(actor, department_id, body, key))


@router.get(
    "/departments/{department_id}/questions/{question_id}/comments",
    response_model=SuccessResponse[Page[ItemView]],
)
def comments(
    department_id: UUID,
    question_id: UUID,
    actor: Actor,
    service: Service,
    offset: Offset = 0,
    limit: Limit = 25,
):
    return SuccessResponse(data=service.items(actor, department_id, question_id, offset, limit))


@router.post(
    "/departments/{department_id}/questions/{question_id}/comments",
    response_model=SuccessResponse[ItemView],
)
def create_comment(
    department_id: UUID, question_id: UUID, body: Content, key: Key, actor: Actor, service: Service
):
    return SuccessResponse(data=service.create(actor, department_id, body, key, question_id))


@router.patch(
    "/departments/{department_id}/items/{item_id}", response_model=SuccessResponse[ItemView]
)
def update_item(
    department_id: UUID,
    item_id: UUID,
    body: QuestionUpdate | CommentUpdate,
    actor: Actor,
    service: Service,
):
    payload = body.model_dump(exclude={"expected_revision"})
    clean = QuestionInput(**payload) if isinstance(body, QuestionUpdate) else Content(**payload)
    return SuccessResponse(
        data=service.change(actor, department_id, item_id, body.expected_revision, clean)
    )


@router.delete("/departments/{department_id}/items/{item_id}", response_model=SuccessResponse[None])
def delete_item(
    department_id: UUID,
    item_id: UUID,
    actor: Actor,
    service: Service,
    expected_revision: Annotated[int, Query(ge=1)],
):
    service.change(actor, department_id, item_id, expected_revision, None)
    return SuccessResponse[None](data=None)
