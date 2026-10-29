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
from app.features.academics.idempotency import KEY_PATTERN
from app.features.academics.models import (
    AcademicActor,
    AcademicRequestView,
    AttendanceChangeView,
    AttendanceOffering,
    AttendanceRecordView,
    CheckInInput,
    CorrectionInput,
    CorrectionResolve,
    CorrectionView,
    EnrollInput,
    EnrollmentView,
    MarkInput,
    MyAttendance,
    Offering,
    PolicyView,
    RequestInput,
    RequestUpdate,
    RevisionInput,
    SessionInput,
    SessionView,
    TranscriptView,
)
from app.features.academics.service import AcademicsError, AcademicsService
from app.schemas.common import ErrorCode, ErrorResponse, SuccessResponse


class PrivateAcademicsRoute(APIRoute):
    def get_route_handler(self) -> Callable:
        original = super().get_route_handler()

        async def private_response(request: Request) -> Response:
            try:
                response = await original(request)
            except AcademicsError as exc:
                response = error_response(
                    exc.code, request.state.request_id, field_errors={"rule": exc.rule}
                )
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
                            "event": "academics.request.failed",
                            "request_id": request.state.request_id,
                        }
                    )
                )
                response = error_response(ErrorCode.INTERNAL, request.state.request_id)
            response.headers["Cache-Control"] = "private, no-store"
            return response

        return private_response


router = APIRouter(
    prefix="/academics",
    tags=["academics-first-pass"],
    route_class=PrivateAcademicsRoute,
    responses={
        status: {"model": ErrorResponse} for status in (400, 401, 403, 404, 409, 429, 500, 503)
    },
)


def get_academics_actor() -> AcademicActor:
    """Approved common auth bridge required. Never trust a client-supplied user/role header."""
    raise ApiError(ErrorCode.UNAVAILABLE)


def get_academics_service() -> AcademicsService:
    """Approved transactional store + injected DemoAcademicPolicy required; no runtime fake."""
    raise ApiError(ErrorCode.UNAVAILABLE)


Actor = Annotated[AcademicActor, Depends(get_academics_actor)]
Service = Annotated[AcademicsService, Depends(get_academics_service)]
IdempotencyKey = Annotated[str, Header(pattern=KEY_PATTERN)]
Limit = Annotated[int, Query(ge=1, le=100)]
ATT = "/attendance/offerings/{offering_id}"


@router.get("/policy", response_model=SuccessResponse[PolicyView])
def demo_policy(actor: Actor, service: Service):
    return SuccessResponse(data=service.policy_view(actor))


@router.get("/offerings", response_model=SuccessResponse[list[Offering]])
def search_offerings(
    actor: Actor,
    service: Service,
    term_id: UUID | None = None,
    q: Annotated[str, Query(max_length=80)] = "",
    limit: Limit = 25,
):
    return SuccessResponse(data=service.search_offerings(actor, term_id, q, limit))


@router.get("/offerings/{offering_id}", response_model=SuccessResponse[Offering])
def get_offering(offering_id: UUID, actor: Actor, service: Service):
    return SuccessResponse(data=service.get_offering(actor, offering_id))


@router.get("/enrollments", response_model=SuccessResponse[list[EnrollmentView]])
def my_enrollments(actor: Actor, service: Service):
    return SuccessResponse(data=service.my_enrollments(actor))


@router.post("/enrollments", response_model=SuccessResponse[EnrollmentView])
def enroll(body: EnrollInput, actor: Actor, service: Service, idempotency_key: IdempotencyKey):
    return SuccessResponse(data=service.enroll(actor, body, idempotency_key))


@router.post("/enrollments/{enrollment_id}/drop", response_model=SuccessResponse[EnrollmentView])
def drop(enrollment_id: UUID, body: RevisionInput, actor: Actor, service: Service):
    return SuccessResponse(data=service.drop(actor, enrollment_id, body))


@router.get("/records", response_model=SuccessResponse[TranscriptView])
def transcript(actor: Actor, service: Service):
    return SuccessResponse(data=service.transcript(actor))


@router.get("/requests", response_model=SuccessResponse[list[AcademicRequestView]])
def my_requests(actor: Actor, service: Service):
    return SuccessResponse(data=service.my_requests(actor))


@router.post("/requests", response_model=SuccessResponse[AcademicRequestView])
def create_request(
    body: RequestInput, actor: Actor, service: Service, idempotency_key: IdempotencyKey
):
    return SuccessResponse(data=service.create_request(actor, body, idempotency_key))


@router.patch("/requests/{request_id}", response_model=SuccessResponse[AcademicRequestView])
def update_request(request_id: UUID, body: RequestUpdate, actor: Actor, service: Service):
    return SuccessResponse(data=service.update_request(actor, request_id, body))


@router.post("/requests/{request_id}/submit", response_model=SuccessResponse[AcademicRequestView])
def submit_request(request_id: UUID, body: RevisionInput, actor: Actor, service: Service):
    return SuccessResponse(data=service.submit_request(actor, request_id, body))


@router.post("/requests/{request_id}/withdraw", response_model=SuccessResponse[AcademicRequestView])
def withdraw_request(request_id: UUID, body: RevisionInput, actor: Actor, service: Service):
    return SuccessResponse(data=service.withdraw_request(actor, request_id, body))


@router.get("/attendance/offerings", response_model=SuccessResponse[list[AttendanceOffering]])
def attendance_offerings(actor: Actor, service: Service, limit: Limit = 25):
    return SuccessResponse(data=service.attendance_offerings(actor, limit))


@router.get(ATT + "/sessions", response_model=SuccessResponse[list[SessionView]])
def sessions(offering_id: UUID, actor: Actor, service: Service):
    return SuccessResponse(data=service.sessions(actor, offering_id))


@router.post(ATT + "/sessions", response_model=SuccessResponse[SessionView])
def open_session(
    offering_id: UUID,
    body: SessionInput,
    actor: Actor,
    service: Service,
    idempotency_key: IdempotencyKey,
):
    return SuccessResponse(data=service.open_session(actor, offering_id, body, idempotency_key))


@router.post(ATT + "/sessions/{session_id}/close", response_model=SuccessResponse[SessionView])
def close_session(
    offering_id: UUID, session_id: UUID, body: RevisionInput, actor: Actor, service: Service
):
    return SuccessResponse(data=service.close_session(actor, offering_id, session_id, body))


@router.post(
    ATT + "/sessions/{session_id}/check-in", response_model=SuccessResponse[AttendanceRecordView]
)
def check_in(
    offering_id: UUID, session_id: UUID, body: CheckInInput, actor: Actor, service: Service
):
    return SuccessResponse(data=service.check_in(actor, offering_id, session_id, body))


@router.get(
    ATT + "/sessions/{session_id}/records",
    response_model=SuccessResponse[list[AttendanceRecordView]],
)
def session_records(offering_id: UUID, session_id: UUID, actor: Actor, service: Service):
    return SuccessResponse(data=service.session_records(actor, offering_id, session_id))


@router.put(
    ATT + "/sessions/{session_id}/records/{member_ref}",
    response_model=SuccessResponse[AttendanceRecordView],
)
def mark(
    offering_id: UUID,
    session_id: UUID,
    member_ref: UUID,
    body: MarkInput,
    actor: Actor,
    service: Service,
):
    return SuccessResponse(data=service.mark(actor, offering_id, session_id, member_ref, body))


@router.get(
    ATT + "/records/{record_id}/history",
    response_model=SuccessResponse[list[AttendanceChangeView]],
)
def record_history(offering_id: UUID, record_id: UUID, actor: Actor, service: Service):
    return SuccessResponse(data=service.record_history(actor, offering_id, record_id))


@router.get(ATT + "/me", response_model=SuccessResponse[MyAttendance])
def my_attendance(offering_id: UUID, actor: Actor, service: Service):
    return SuccessResponse(data=service.my_attendance(actor, offering_id))


@router.post(
    ATT + "/records/{record_id}/corrections", response_model=SuccessResponse[CorrectionView]
)
def request_correction(
    offering_id: UUID,
    record_id: UUID,
    body: CorrectionInput,
    actor: Actor,
    service: Service,
    idempotency_key: IdempotencyKey,
):
    return SuccessResponse(
        data=service.request_correction(actor, offering_id, record_id, body, idempotency_key)
    )


@router.get(ATT + "/corrections", response_model=SuccessResponse[list[CorrectionView]])
def corrections(offering_id: UUID, actor: Actor, service: Service):
    return SuccessResponse(data=service.corrections(actor, offering_id))


@router.post(
    ATT + "/corrections/{correction_id}/resolve", response_model=SuccessResponse[CorrectionView]
)
def resolve_correction(
    offering_id: UUID,
    correction_id: UUID,
    body: CorrectionResolve,
    actor: Actor,
    service: Service,
):
    return SuccessResponse(data=service.resolve_correction(actor, offering_id, correction_id, body))
