import json
from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request, Response
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
from app.schemas.common import ErrorCode, ErrorResponse, SuccessResponse

from .models import ProfileActor, ProfileUpdate, ProfileView
from .service import ProfileService


class PrivateProfileRoute(APIRoute):
    def get_route_handler(self) -> Callable:
        handler = super().get_route_handler()

        async def private(request: Request) -> Response:
            try:
                response = await handler(request)
            except ApiError as exc:
                response = await api_error_handler(request, exc)
            except RequestValidationError as exc:
                response = await validation_error_handler(request, exc)
            except HTTPException as exc:
                response = await http_error_handler(request, exc)
            except Exception:
                logger.error(
                    json.dumps({"event": "profiles.failed", "request_id": request.state.request_id})
                )
                response = error_response(ErrorCode.INTERNAL, request.state.request_id)
            response.headers["Cache-Control"] = "private, no-store"
            return response

        return private


router = APIRouter(
    prefix="/profiles",
    tags=["self-profile-firstpass"],
    route_class=PrivateProfileRoute,
    responses={status: {"model": ErrorResponse} for status in (400, 401, 403, 404, 409, 500, 503)},
)


def get_profile_actor() -> ProfileActor:
    raise ApiError(ErrorCode.UNAVAILABLE)


def get_profile_service() -> ProfileService:
    raise ApiError(ErrorCode.UNAVAILABLE)


Actor = Annotated[ProfileActor, Depends(get_profile_actor)]
Service = Annotated[ProfileService, Depends(get_profile_service)]


@router.get("/me", response_model=SuccessResponse[ProfileView])
def get_profile(actor: Actor, service: Service):
    return SuccessResponse(data=service.get(actor))


@router.put("/me", response_model=SuccessResponse[ProfileView])
def update_profile(
    body: ProfileUpdate,
    actor: Actor,
    service: Service,
    idempotency_key: Annotated[
        str, Header(min_length=16, max_length=100, pattern=r"^[A-Za-z0-9-]+$")
    ],
):
    return SuccessResponse(data=service.update(actor, body, idempotency_key))
