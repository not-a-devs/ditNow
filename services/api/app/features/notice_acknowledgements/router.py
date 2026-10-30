import json
from collections.abc import Callable
from typing import Annotated
from uuid import UUID

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
from app.features.notice_acknowledgements.models import (
    AckInput,
    AckReceipt,
    AckRequestInput,
    AckRequestView,
    AckSummary,
    OwnState,
)
from app.features.notice_acknowledgements.ports import Actor
from app.features.notice_acknowledgements.service import (
    KEY_PATTERN,
    NoticeAcknowledgementService,
)
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
                            "event": "notice_acknowledgements.request.failed",
                            "request_id": request.state.request_id,
                        }
                    )
                )
                response = error_response(ErrorCode.INTERNAL, request.state.request_id)
            response.headers["Cache-Control"] = "private, no-store"
            return response

        return handle


def get_actor() -> Actor:
    """Only the approved common identity bridge may supply this; no header/body identity."""
    raise ApiError(ErrorCode.UNAVAILABLE)


def get_service(request: Request) -> NoticeAcknowledgementService:
    service = getattr(request.app.state, "notice_acknowledgements", None)
    if not isinstance(service, NoticeAcknowledgementService):
        raise ApiError(ErrorCode.UNAVAILABLE)
    return service


CurrentActor = Annotated[Actor, Depends(get_actor)]
Service = Annotated[NoticeAcknowledgementService, Depends(get_service)]
Key = Annotated[str, Header(alias="Idempotency-Key", pattern=KEY_PATTERN)]
router = APIRouter(
    prefix="/notice-acknowledgements",
    tags=["notice-acknowledgements-first-pass"],
    route_class=PrivateRoute,
)


@router.post("/request", response_model=SuccessResponse[AckRequestView])
def create_request(body: AckRequestInput, key: Key, actor: CurrentActor, service: Service):
    return SuccessResponse(data=service.request(actor, body, key))


@router.get("/{notice_id}", response_model=SuccessResponse[OwnState])
def own_state(notice_id: UUID, actor: CurrentActor, service: Service):
    return SuccessResponse(data=service.state(actor, notice_id))


@router.post("/{notice_id}/ack", response_model=SuccessResponse[AckReceipt])
def acknowledge(notice_id: UUID, body: AckInput, key: Key, actor: CurrentActor, service: Service):
    return SuccessResponse(data=service.acknowledge(actor, notice_id, body, key))


@router.get("/{notice_id}/summary", response_model=SuccessResponse[AckSummary])
def summary(notice_id: UUID, actor: CurrentActor, service: Service):
    return SuccessResponse(data=service.summary(actor, notice_id))
