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
from app.features.student_life.models import (
    CancelInput,
    ChangeInput,
    CreateInput,
    GuidePage,
    LifeActor,
    LifeOverview,
    LifeRequestView,
)
from app.features.student_life.service import StudentLifeService
from app.schemas.common import ErrorCode, ErrorResponse, SuccessResponse


class LifeRoute(APIRoute):
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
    prefix="/student-life",
    tags=["student-life-first-pass"],
    route_class=LifeRoute,
    responses={s: {"model": ErrorResponse} for s in (400, 401, 403, 404, 409, 500, 503)},
)


def get_life_actor() -> LifeActor:
    raise ApiError(ErrorCode.UNAVAILABLE)


def get_life_service() -> StudentLifeService:
    raise ApiError(ErrorCode.UNAVAILABLE)


Actor = Annotated[LifeActor, Depends(get_life_actor)]
Service = Annotated[StudentLifeService, Depends(get_life_service)]
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


@router.get("/me", response_model=SuccessResponse[LifeOverview])
def overview(actor: Actor, service: Service):
    return SuccessResponse(data=service.overview(actor))


@router.post("/me/requests", response_model=SuccessResponse[LifeRequestView], status_code=201)
def create(actor: Actor, service: Service, body: CreateInput, key: Key):
    row = service.create(actor, body, key)
    return SuccessResponse(data=row, resource_version=row.revision)


@router.patch("/me/requests/{request_id}", response_model=SuccessResponse[LifeRequestView])
def update(request_id: UUID, actor: Actor, service: Service, body: ChangeInput, key: Key):
    row = service.change(actor, request_id, body, key)
    return SuccessResponse(data=row, resource_version=row.revision)


@router.post("/me/requests/{request_id}/cancel", response_model=SuccessResponse[LifeRequestView])
def cancel(request_id: UUID, actor: Actor, service: Service, body: CancelInput, key: Key):
    row = service.change(actor, request_id, body, key, cancel=True)
    return SuccessResponse(data=row, resource_version=row.revision)
