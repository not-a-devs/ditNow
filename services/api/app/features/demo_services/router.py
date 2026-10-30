from typing import Annotated
from uuid import UUID, uuid4

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
from app.features.demo_services.models import (
    AdvanceInput,
    CreateInput,
    DeletedDemo,
    DemoActor,
    DemoItem,
    DemoPage,
)
from app.features.demo_services.service import DemoServices
from app.schemas.common import ErrorCode, ErrorResponse, SuccessResponse


class DemoRoute(APIRoute):
    def get_route_handler(self):
        original = super().get_route_handler()

        async def handle(request: Request) -> Response:
            if not getattr(request.state, "request_id", None):
                request.state.request_id = str(uuid4())
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
    prefix="/me/demo-services",
    tags=["fictional-student-services"],
    route_class=DemoRoute,
    responses={s: {"model": ErrorResponse} for s in (400, 401, 403, 404, 409, 429, 500, 503)},
)


def get_demo_actor() -> DemoActor:
    """Root integrator must override with a current verified common-context identity."""
    raise ApiError(ErrorCode.UNAVAILABLE)


def get_demo_service(request: Request) -> DemoServices:
    service = getattr(request.app.state, "demo_services", None)
    if not isinstance(service, DemoServices):
        raise ApiError(ErrorCode.UNAVAILABLE)
    return service


Actor = Annotated[DemoActor, Depends(get_demo_actor)]
Service = Annotated[DemoServices, Depends(get_demo_service)]
Key = Annotated[
    str,
    Header(alias="Idempotency-Key", min_length=16, max_length=100, pattern=r"^[A-Za-z0-9_-]+$"),
]


@router.get("", response_model=SuccessResponse[DemoPage])
def list_services(actor: Actor, service: Service):
    return SuccessResponse(data=service.list(actor))


@router.post("", response_model=SuccessResponse[DemoItem], status_code=201)
def create(body: CreateInput, actor: Actor, service: Service, key: Key):
    item = service.create(actor, body, key)
    return SuccessResponse(data=item, resource_version=item.revision)


@router.post("/{identifier}/advance", response_model=SuccessResponse[DemoItem])
def advance(identifier: UUID, body: AdvanceInput, actor: Actor, service: Service, key: Key):
    item = service.advance(actor, identifier, body, key)
    return SuccessResponse(data=item, resource_version=item.revision)


@router.delete("/{identifier}", response_model=SuccessResponse[DeletedDemo])
def delete(
    identifier: UUID,
    actor: Actor,
    service: Service,
    revision: Annotated[int, Query(ge=1, le=2_147_483_647)],
):
    return SuccessResponse(data=service.delete(actor, identifier, revision))
