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
from app.features.classrooms.models import (
    ClassroomActor,
    ClassroomWorkspace,
    Offering,
    QuestionChange,
    QuestionInput,
    QuestionView,
    ResolutionInput,
    SubmissionInput,
    SubmissionView,
)
from app.features.classrooms.service import ClassroomService
from app.schemas.common import ErrorCode, ErrorResponse, SuccessResponse


class PrivateClassroomRoute(APIRoute):
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
                            "event": "classroom.request.failed",
                            "request_id": request.state.request_id,
                        }
                    )
                )
                response = error_response(ErrorCode.INTERNAL, request.state.request_id)
            response.headers["Cache-Control"] = "private, no-store"
            return response

        return private_response


router = APIRouter(
    prefix="/classrooms",
    tags=["classrooms-first-pass"],
    route_class=PrivateClassroomRoute,
    responses={status: {"model": ErrorResponse} for status in (400, 401, 403, 404, 409, 500, 503)},
)


def get_classroom_actor() -> ClassroomActor:
    """Approved common auth bridge required. Never trust a client-supplied user/role header."""
    raise ApiError(ErrorCode.UNAVAILABLE)


def get_classroom_service() -> ClassroomService:
    """Approved transactional enrollment/store adapter required; no runtime fake fallback."""
    raise ApiError(ErrorCode.UNAVAILABLE)


Actor = Annotated[ClassroomActor, Depends(get_classroom_actor)]
Service = Annotated[ClassroomService, Depends(get_classroom_service)]


@router.get("", response_model=SuccessResponse[list[Offering]])
def list_classrooms(
    actor: Actor, service: Service, limit: Annotated[int, Query(ge=1, le=100)] = 25
):
    return SuccessResponse(data=service.list_offerings(actor, limit))


@router.get("/{offering_id}", response_model=SuccessResponse[ClassroomWorkspace])
def get_classroom(offering_id: UUID, actor: Actor, service: Service):
    return SuccessResponse(data=service.workspace(actor, offering_id))


@router.post("/{offering_id}/questions", response_model=SuccessResponse[QuestionView])
def create_question(
    offering_id: UUID,
    body: QuestionInput,
    actor: Actor,
    service: Service,
    idempotency_key: Annotated[
        str, Header(min_length=16, max_length=100, pattern=r"^[A-Za-z0-9-]+$")
    ],
):
    return SuccessResponse(data=service.create_question(actor, offering_id, body, idempotency_key))


@router.post(
    "/{offering_id}/questions/{question_id}/answer", response_model=SuccessResponse[QuestionView]
)
def answer_question(
    offering_id: UUID, question_id: UUID, body: QuestionChange, actor: Actor, service: Service
):
    return SuccessResponse(data=service.answer_question(actor, offering_id, question_id, body))


@router.post(
    "/{offering_id}/questions/{question_id}/resolve", response_model=SuccessResponse[QuestionView]
)
def resolve_question(
    offering_id: UUID, question_id: UUID, body: ResolutionInput, actor: Actor, service: Service
):
    return SuccessResponse(
        data=service.resolve_question(actor, offering_id, question_id, body.expected_revision)
    )


@router.put(
    "/{offering_id}/assignments/{assignment_id}/submission",
    response_model=SuccessResponse[SubmissionView],
)
def submit_text(
    offering_id: UUID, assignment_id: UUID, body: SubmissionInput, actor: Actor, service: Service
):
    return SuccessResponse(data=service.submit_text(actor, offering_id, assignment_id, body))
