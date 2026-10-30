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
from app.features.admin_audit_queue.models import (
    AuditActor,
    AuditCategory,
    AuditItemView,
    AuditPatchInput,
    AuditQueuePage,
    AuditStatus,
)
from app.features.admin_audit_queue.service import AdminAuditQueueService
from app.schemas.common import ErrorCode, ErrorResponse, SuccessResponse


class PrivateNoStoreRoute(APIRoute):
    """Every response, including errors and validation failures, is private/no-store."""

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
                        {
                            "event": "admin_audit_queue.failed",
                            "request_id": request.state.request_id,
                        }
                    )
                )
                response = error_response(ErrorCode.INTERNAL, request.state.request_id)
            response.headers["Cache-Control"] = "private, no-store"
            return response

        return handle


router = APIRouter(
    prefix="/admin-audit-queue",
    tags=["admin-audit-queue-demo"],
    route_class=PrivateNoStoreRoute,
    responses={s: {"model": ErrorResponse} for s in (400, 401, 403, 404, 409, 500, 503)},
)


def get_admin_audit_actor() -> AuditActor:
    # Dormant: a trusted identity bridge must override this. No client-provided identity.
    raise ApiError(ErrorCode.UNAVAILABLE)


def get_admin_audit_service(request: Request) -> AdminAuditQueueService:
    service = getattr(request.app.state, "admin_audit_queue", None)
    if not isinstance(service, AdminAuditQueueService):
        raise ApiError(ErrorCode.UNAVAILABLE)
    return service


Actor = Annotated[AuditActor, Depends(get_admin_audit_actor)]
Service = Annotated[AdminAuditQueueService, Depends(get_admin_audit_service)]
Key = Annotated[
    str | None,
    Header(alias="Idempotency-Key", min_length=16, max_length=100, pattern=r"^[A-Za-z0-9-]+$"),
]


@router.get("", response_model=SuccessResponse[AuditQueuePage])
def list_queue(
    actor: Actor,
    service: Service,
    status: Annotated[AuditStatus | None, Query()] = None,
    category: Annotated[AuditCategory | None, Query()] = None,
):
    return SuccessResponse(data=service.list_items(actor, status, category))


@router.get("/{item_id}", response_model=SuccessResponse[AuditItemView])
def read_item(item_id: UUID, actor: Actor, service: Service):
    return SuccessResponse(data=service.get(actor, item_id))


@router.patch("/{item_id}", response_model=SuccessResponse[AuditItemView])
def patch_item(
    item_id: UUID, body: AuditPatchInput, actor: Actor, service: Service, key: Key = None
):
    return SuccessResponse(data=service.patch(actor, item_id, body, key))
