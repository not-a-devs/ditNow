"""Admin change proposal routes (not mounted; the root owner includes this under ``/api/v1``).

Defaults fail closed with 503: ``get_actor`` must be overridden by the trusted auth owner and the
service must be injected as ``app.state.admin_change_requests``. Every response, including errors,
carries ``Cache-Control: private, no-store``. There is no approval or execution endpoint.
"""

import json
from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Path, Query, Request, Response, status
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

from .models import (
    ID_PATTERN,
    KEY_PATTERN,
    REVISION_MAX,
    AdminChangeActor,
    ProposalCreate,
    ProposalList,
    ProposalSubmit,
    ProposalView,
)
from .service import AdminChangeRequestService


class PrivateNoStoreRoute(APIRoute):
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
                event = {"event": "admin_change_requests.failed"}
                logger.error(json.dumps({**event, "request_id": request.state.request_id}))
                response = error_response(ErrorCode.INTERNAL, request.state.request_id)
            response.headers["Cache-Control"] = "private, no-store"
            return response

        return private


router = APIRouter(
    prefix="/admin-change-requests",
    tags=["admin-change-requests-demo"],
    route_class=PrivateNoStoreRoute,
    responses={code: {"model": ErrorResponse} for code in (400, 401, 403, 404, 409, 429, 500, 503)},
)


def get_actor() -> AdminChangeActor | None:
    """Trusted server auth owner overrides this; ``None`` means unauthenticated (401)."""
    raise ApiError(ErrorCode.UNAVAILABLE)


def get_service(request: Request) -> AdminChangeRequestService:
    service = getattr(request.app.state, "admin_change_requests", None)
    if not isinstance(service, AdminChangeRequestService):
        raise ApiError(ErrorCode.UNAVAILABLE)
    return service


Actor = Annotated[AdminChangeActor | None, Depends(get_actor)]
Service = Annotated[AdminChangeRequestService, Depends(get_service)]
ProposalId = Annotated[str, Path(pattern=ID_PATTERN)]
IdempotencyKey = Annotated[str, Header(alias="Idempotency-Key", pattern=KEY_PATTERN)]


@router.get("", response_model=SuccessResponse[ProposalList])
def list_proposals(actor: Actor, service: Service):
    return SuccessResponse(data=service.list_own(actor))


@router.post("", response_model=SuccessResponse[ProposalView], status_code=status.HTTP_201_CREATED)
def create_proposal(body: ProposalCreate, actor: Actor, service: Service, key: IdempotencyKey):
    return SuccessResponse(data=service.create(actor, body, key))


@router.post("/{proposal_id}/submit", response_model=SuccessResponse[ProposalView])
def submit_proposal(
    proposal_id: ProposalId,
    body: ProposalSubmit,
    actor: Actor,
    service: Service,
    key: IdempotencyKey,
):
    return SuccessResponse(data=service.submit(actor, proposal_id, body, key))


@router.delete("/{proposal_id}", response_model=SuccessResponse[ProposalView])
def withdraw_proposal(
    proposal_id: ProposalId,
    actor: Actor,
    service: Service,
    revision: Annotated[int, Query(ge=1, le=REVISION_MAX)],
):
    return SuccessResponse(data=service.withdraw(actor, proposal_id, revision))
