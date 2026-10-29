import json
from collections.abc import Callable
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response
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
from app.features.action_center.models import (
    HomeSummary,
    NotificationPage,
    NotificationView,
    ReadInput,
)
from app.features.action_center.service import ActionCenterService
from app.schemas.common import ErrorCode, SuccessResponse


class PrivateActionRoute(APIRoute):
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
                            "event": "action_center.request.failed",
                            "request_id": request.state.request_id,
                        }
                    )
                )
                response = error_response(ErrorCode.INTERNAL, request.state.request_id)
            response.headers["Cache-Control"] = "private, no-store"
            return response

        return handle


def get_actor() -> UUID:
    """Only the approved common identity bridge can supply this; no header/query actor."""
    raise ApiError(ErrorCode.UNAVAILABLE)


def get_service() -> ActionCenterService:
    raise ApiError(ErrorCode.UNAVAILABLE)


Actor = Annotated[UUID, Depends(get_actor)]
Service = Annotated[ActionCenterService, Depends(get_service)]
router = APIRouter(
    prefix="/action-center", tags=["action-center-first-pass"], route_class=PrivateActionRoute
)


@router.get("/summary", response_model=SuccessResponse[HomeSummary])
def summary(actor: Actor, service: Service):
    return SuccessResponse(data=service.summary(actor))


@router.get("/notifications", response_model=SuccessResponse[NotificationPage])
def notifications(
    actor: Actor,
    service: Service,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
):
    return SuccessResponse(data=service.inbox(actor, offset, limit))


@router.post(
    "/notifications/{notification_id}/read", response_model=SuccessResponse[NotificationView]
)
def read(notification_id: UUID, body: ReadInput, actor: Actor, service: Service):
    return SuccessResponse(data=service.mark_read(actor, notification_id, body.expected_revision))
