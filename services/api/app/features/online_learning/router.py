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
from app.features.online_learning.models import (
    AttemptView,
    ExamView,
    LearningActor,
    OfferingRef,
    ProgressInput,
    ProgressView,
    StartInput,
    SubmitInput,
    Workspace,
)
from app.features.online_learning.service import OnlineLearningService
from app.schemas.common import ErrorCode, ErrorResponse, SuccessResponse


class PrivateLearningRoute(APIRoute):
    def get_route_handler(self) -> Callable:
        original = super().get_route_handler()

        async def private_response(request: Request) -> Response:
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
                            "event": "online_learning.request.failed",
                            "request_id": request.state.request_id,
                        }
                    )
                )
                response = error_response(ErrorCode.INTERNAL, request.state.request_id)
            response.headers["Cache-Control"] = "private, no-store"
            return response

        return private_response


router = APIRouter(
    prefix="/online-learning",
    tags=["online-learning-first-pass"],
    route_class=PrivateLearningRoute,
    responses={status: {"model": ErrorResponse} for status in (400, 401, 403, 404, 409, 500, 503)},
)


def get_learning_actor() -> LearningActor:
    """Approved common UUID/session bridge required. No client role/subject headers."""
    raise ApiError(ErrorCode.UNAVAILABLE)


def get_learning_service() -> OnlineLearningService:
    """Current enrollment, explicit demo policy and transactional DB adapter required."""
    raise ApiError(ErrorCode.UNAVAILABLE)


Actor = Annotated[LearningActor, Depends(get_learning_actor)]
Service = Annotated[OnlineLearningService, Depends(get_learning_service)]
Key = Annotated[str, Header(min_length=16, max_length=100, pattern=r"^[A-Za-z0-9-]+$")]


@router.get("", response_model=SuccessResponse[list[OfferingRef]])
def offerings(actor: Actor, service: Service, limit: Annotated[int, Query(ge=1, le=50)] = 20):
    return SuccessResponse(data=service.offerings(actor, limit))


@router.get("/{offering_id}", response_model=SuccessResponse[Workspace])
def workspace(offering_id: UUID, actor: Actor, service: Service):
    return SuccessResponse(data=service.workspace(actor, offering_id))


@router.put("/{offering_id}/units/{unit_id}/progress", response_model=SuccessResponse[ProgressView])
def progress(
    offering_id: UUID,
    unit_id: UUID,
    body: ProgressInput,
    actor: Actor,
    service: Service,
    idempotency_key: Key,
):
    return SuccessResponse(
        data=service.mark_step(actor, offering_id, unit_id, body, idempotency_key)
    )


@router.get("/{offering_id}/exams/{exam_id}", response_model=SuccessResponse[ExamView])
def exam(offering_id: UUID, exam_id: UUID, actor: Actor, service: Service):
    return SuccessResponse(data=service.exam(actor, offering_id, exam_id))


@router.post("/{offering_id}/exams/{exam_id}/attempts", response_model=SuccessResponse[AttemptView])
def start(
    offering_id: UUID,
    exam_id: UUID,
    body: StartInput,
    actor: Actor,
    service: Service,
    idempotency_key: Key,
):
    return SuccessResponse(data=service.start(actor, offering_id, exam_id, body, idempotency_key))


@router.get(
    "/{offering_id}/exams/{exam_id}/attempts/{attempt_id}",
    response_model=SuccessResponse[AttemptView],
)
def attempt(offering_id: UUID, exam_id: UUID, attempt_id: UUID, actor: Actor, service: Service):
    return SuccessResponse(data=service.attempt(actor, offering_id, exam_id, attempt_id))


@router.post(
    "/{offering_id}/exams/{exam_id}/attempts/{attempt_id}/submit",
    response_model=SuccessResponse[AttemptView],
)
def submit(
    offering_id: UUID,
    exam_id: UUID,
    attempt_id: UUID,
    body: SubmitInput,
    actor: Actor,
    service: Service,
    idempotency_key: Key,
):
    return SuccessResponse(
        data=service.submit(actor, offering_id, exam_id, attempt_id, body, idempotency_key)
    )
