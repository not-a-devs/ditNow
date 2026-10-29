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
from app.features.library.models import (
    BookingView,
    CatalogPage,
    LibraryActor,
    LibraryOverview,
    LoanView,
    RevisionInput,
    Slot,
    WishInput,
    WishView,
)
from app.features.library.service import LibraryService
from app.schemas.common import ErrorCode, ErrorResponse, SuccessResponse


class LibraryRoute(APIRoute):
    def get_route_handler(self) -> Callable:
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
                logger.error(
                    json.dumps(
                        {"event": "library.request.failed", "request_id": request.state.request_id}
                    )
                )
                response = error_response(ErrorCode.INTERNAL, request.state.request_id)
            response.headers["Cache-Control"] = "private, no-store"
            return response

        return handle


router = APIRouter(
    prefix="/library",
    tags=["library-first-pass"],
    route_class=LibraryRoute,
    responses={status: {"model": ErrorResponse} for status in (400, 401, 403, 404, 409, 500, 503)},
)


def get_library_actor() -> LibraryActor:
    raise ApiError(ErrorCode.UNAVAILABLE)


def get_library_service() -> LibraryService:
    raise ApiError(ErrorCode.UNAVAILABLE)


Actor = Annotated[LibraryActor, Depends(get_library_actor)]
Service = Annotated[LibraryService, Depends(get_library_service)]
Key = Annotated[
    str, Header(alias="Idempotency-Key", min_length=16, max_length=100, pattern=r"^[A-Za-z0-9-]+$")
]


@router.get("/catalog", response_model=SuccessResponse[CatalogPage])
def catalog(
    service: Service,
    q: Annotated[str, Query(max_length=120)] = "",
    offset: Annotated[int, Query(ge=0, le=10000)] = 0,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
):
    return SuccessResponse(data=service.catalog(q, offset, limit))


@router.get("/slots", response_model=SuccessResponse[list[Slot]])
def slots(service: Service):
    return SuccessResponse(data=service.slots())


@router.get("/me", response_model=SuccessResponse[LibraryOverview])
def overview(actor: Actor, service: Service):
    return SuccessResponse(data=service.overview(actor))


@router.post("/me/loans/{loan_id}/renew", response_model=SuccessResponse[LoanView])
def renew(loan_id: UUID, body: RevisionInput, key: Key, actor: Actor, service: Service):
    return SuccessResponse(data=service.renew(actor, loan_id, body, key))


@router.post("/me/wishes", response_model=SuccessResponse[WishView])
def request_title(body: WishInput, key: Key, actor: Actor, service: Service):
    return SuccessResponse(data=service.request_title(actor, body, key))


@router.post("/me/slots/{slot_id}/reserve", response_model=SuccessResponse[BookingView])
def reserve(slot_id: UUID, body: RevisionInput, key: Key, actor: Actor, service: Service):
    return SuccessResponse(data=service.reserve(actor, slot_id, body, key))


@router.post("/me/bookings/{booking_id}/cancel", response_model=SuccessResponse[BookingView])
def cancel(booking_id: UUID, body: RevisionInput, key: Key, actor: Actor, service: Service):
    return SuccessResponse(data=service.cancel(actor, booking_id, body, key))
