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
from app.features.admissions.models import (
    ApplicantActor,
    ApplicantOverview,
    ApplicationView,
    DraftCreate,
    DraftUpdate,
    GuidePage,
    TransitionInput,
)
from app.features.admissions.service import AdmissionsService
from app.schemas.common import ErrorCode, ErrorResponse, SuccessResponse


class AdmissionsRoute(APIRoute):
    def get_route_handler(self):
        original = super().get_route_handler()

        async def handle(request: Request) -> Response:
            try:
                response = await original(request)
            except ApiError as exc:
                response = await api_error_handler(request, exc)
            except RequestValidationError as exc:
                response = await validation_error_handler(request, exc)
            except HTTPException as exc:
                response = await http_error_handler(request, exc)
            except Exception:
                response = error_response(ErrorCode.INTERNAL, request.state.request_id)
            response.headers["Cache-Control"] = "private, no-store"
            return response

        return handle


router = APIRouter(
    prefix="/admissions",
    tags=["admissions-first-pass"],
    route_class=AdmissionsRoute,
    responses={s: {"model": ErrorResponse} for s in (400, 401, 403, 404, 409, 500, 503)},
)


def get_applicant_actor() -> ApplicantActor:
    raise ApiError(ErrorCode.UNAVAILABLE)


def get_admissions_service() -> AdmissionsService:
    raise ApiError(ErrorCode.UNAVAILABLE)


Actor = Annotated[ApplicantActor, Depends(get_applicant_actor)]
Service = Annotated[AdmissionsService, Depends(get_admissions_service)]
Key = Annotated[
    str, Header(alias="Idempotency-Key", min_length=16, max_length=100, pattern=r"^[A-Za-z0-9-]+$")
]


@router.get("/guides", response_model=SuccessResponse[GuidePage])
def guides(
    service: Service,
    offset: Annotated[int, Query(ge=0, le=10000)] = 0,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
):
    return SuccessResponse(data=service.guides(offset, limit))


@router.get("/me", response_model=SuccessResponse[ApplicantOverview])
def overview(actor: Actor, service: Service):
    return SuccessResponse(data=service.overview(actor))


@router.post("/me/applications", response_model=SuccessResponse[ApplicationView], status_code=201)
def create(actor: Actor, service: Service, body: DraftCreate, key: Key):
    return SuccessResponse(data=service.create(actor, body, key))


@router.patch("/me/applications/{application_id}", response_model=SuccessResponse[ApplicationView])
def update(application_id: UUID, actor: Actor, service: Service, body: DraftUpdate, key: Key):
    return SuccessResponse(data=service.change(actor, application_id, body, key, "update"))


@router.post(
    "/me/applications/{application_id}/submit", response_model=SuccessResponse[ApplicationView]
)
def submit(application_id: UUID, actor: Actor, service: Service, body: TransitionInput, key: Key):
    return SuccessResponse(data=service.change(actor, application_id, body, key, "submit"))


@router.post(
    "/me/applications/{application_id}/withdraw", response_model=SuccessResponse[ApplicationView]
)
def withdraw(application_id: UUID, actor: Actor, service: Service, body: TransitionInput, key: Key):
    return SuccessResponse(data=service.change(actor, application_id, body, key, "withdraw"))
