"""DEMO attendance sandbox routes (not mounted; the root owner includes this under ``/api/v1``).

Both dependencies fail closed with 503 ``UNAVAILABLE``. The root binds the common auth actor by
overriding ``get_actor`` (return the current user's UUID, or ``None`` for 401) and installs a
``DemoAttendanceStore`` on ``app.state.demo_attendance``. The caller's identity is never read from
the request body, query or headers. All responses carry ``Cache-Control: private, no-store``.
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response, status

from app.core.errors import ApiError, error_response
from app.features.collaboration.router import PrivateNoStoreRoute
from app.features.demo_attendance.schemas import (
    DEMO_CODE,
    CheckInRequest,
    CheckInResult,
    DemoAttendanceState,
    DemoCardView,
    demo_card_view,
)
from app.features.demo_attendance.store import DemoAttendanceFull, DemoAttendanceStore
from app.schemas.common import ErrorCode, ErrorResponse, SuccessResponse

STATE_ATTR = "demo_attendance"


def get_actor() -> UUID | None:
    raise ApiError(ErrorCode.UNAVAILABLE)


def get_store(request: Request) -> DemoAttendanceStore:
    store = getattr(request.app.state, STATE_ATTR, None)
    if not isinstance(store, DemoAttendanceStore):
        raise ApiError(ErrorCode.UNAVAILABLE)
    return store


def current_actor(actor: Annotated[UUID | None, Depends(get_actor)]) -> UUID:
    if not isinstance(actor, UUID):
        raise ApiError(ErrorCode.UNAUTHORIZED)
    return actor


Actor = Annotated[UUID, Depends(current_actor)]


def demo_store(
    _: Actor,  # authentication is decided before the store is ever resolved
    store: Annotated[DemoAttendanceStore, Depends(get_store)],
) -> DemoAttendanceStore:
    return store


Store = Annotated[DemoAttendanceStore, Depends(demo_store)]

router = APIRouter(
    prefix="/me/demo-attendance",
    tags=["demo-attendance"],
    route_class=PrivateNoStoreRoute,
    responses={code: {"model": ErrorResponse} for code in (400, 401, 422, 500, 503)},
)


@router.get("/card", response_model=SuccessResponse[DemoCardView])
def get_card(_: Actor, __: Store):
    return SuccessResponse(data=demo_card_view())


@router.get("/state", response_model=SuccessResponse[DemoAttendanceState])
def get_state(actor: Actor, store: Store):
    record = store.get(actor)
    return SuccessResponse(
        data=DemoAttendanceState(
            checked_in=record is not None,
            checked_in_at=record.checked_in_at if record else None,
        )
    )


@router.post(
    "/check-in",
    response_model=SuccessResponse[CheckInResult],
    status_code=status.HTTP_201_CREATED,
)
def check_in(
    actor: Actor, store: Store, payload: CheckInRequest, request: Request, response: Response
):
    if payload.code != DEMO_CODE:
        return error_response(
            ErrorCode.VALIDATION,
            request.state.request_id,
            status_code=422,
            field_errors={"code": "시연 코드가 일치하지 않습니다."},
        )
    try:
        record, created = store.check_in(actor)
    except DemoAttendanceFull:
        raise ApiError(ErrorCode.UNAVAILABLE) from None
    if not created:
        response.status_code = status.HTTP_200_OK
    return SuccessResponse(
        data=CheckInResult(checked_in_at=record.checked_in_at, replayed=not created)
    )
