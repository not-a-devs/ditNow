"""API-JOB routes (relative paths; root would mount under /api/v1). NOT mounted by this task.

Defaults fail closed (503): no auth provider, unit of work, catalog or DemoCareerPolicy is
configured here, and none is created at import time. Every response, success or error, carries
`Cache-Control: private, no-store`.
"""

import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
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
from app.features.careers.domain import (
    CareerGrant,
    CareersActor,
    DemoCareerPolicy,
    require_actor,
    require_grant,
)
from app.features.careers.ports import CareersUnitOfWork
from app.features.careers.schemas import (
    ApplicationCancel,
    ApplicationCreate,
    ApplicationData,
    ApplicationListData,
    ContestPageData,
    DeletedData,
    EmployerDraftCreate,
    EmployerDraftData,
    EmployerDraftListData,
    EmployerDraftPatch,
    JobPageData,
    JobSummaryData,
    ProfileCreate,
    ProfileData,
    ProfileEnvelope,
    ProfilePatch,
    ProgramListData,
)
from app.features.careers.service import CareersService
from app.features.opportunities.repository import OpportunityCatalog
from app.schemas.common import ErrorCode, ErrorResponse, SuccessResponse, utc_now

PRIVATE_CACHE = "private, no-store"
REPLAY_HEADER = "Idempotent-Replayed"
_ERRORS = {code: {"model": ErrorResponse} for code in (400, 401, 403, 404, 409, 500, 503)}
_IF_MATCH = re.compile(r'(?:"(?P<quoted>[1-9][0-9]{0,8})"|(?P<bare>[1-9][0-9]{0,8}))')

IfMatch = Annotated[str, Header(alias="If-Match", max_length=16)]
IdempotencyKey = Annotated[
    str, Header(alias="Idempotency-Key", min_length=8, max_length=100, pattern=r"^[A-Za-z0-9_-]+$")
]


def parse_if_match(value: str) -> int:
    """One strong revision only (`3` or `"3"`); weak tags, lists and `*` are 400."""
    match = _IF_MATCH.fullmatch(value.strip(" \t"))
    if match is None:
        raise ApiError(ErrorCode.VALIDATION)
    return int(match["quoted"] or match["bare"])


class PrivateCareersRoute(APIRoute):
    def get_route_handler(self) -> Callable:
        original = super().get_route_handler()

        async def private_response(request: Request) -> Response:
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
                        {"event": "careers.request.failed", "request_id": request.state.request_id}
                    )
                )
                response = error_response(ErrorCode.INTERNAL, request.state.request_id)
            response.headers["Cache-Control"] = PRIVATE_CACHE
            return response

        return private_response


def auth_not_configured() -> CareersActor | None:
    raise ApiError(ErrorCode.UNAVAILABLE)


def not_configured() -> object:
    raise ApiError(ErrorCode.UNAVAILABLE)


@dataclass(frozen=True)
class CareersDependencies:
    """Root/auth/DB owners replace these. `actor` returns None for anonymous (-> 401) and must
    come from the shared verified session; grants come from the unit of work."""

    actor: Callable[..., CareersActor | None] = auth_not_configured
    catalog: Callable[..., OpportunityCatalog] = not_configured
    uow: Callable[..., CareersUnitOfWork] = not_configured
    policy: Callable[..., DemoCareerPolicy] = not_configured
    clock: Callable[[], datetime] = utc_now
    id_factory: Callable[[], UUID] | None = None


def create_careers_router(deps: CareersDependencies | None = None) -> APIRouter:
    deps = deps or CareersDependencies()
    router = APIRouter(
        prefix="/careers", tags=["careers"], responses=_ERRORS, route_class=PrivateCareersRoute
    )
    extra = {"id_factory": deps.id_factory} if deps.id_factory else {}

    def public_service(
        policy: Annotated[DemoCareerPolicy, Depends(deps.policy)],
        catalog: Annotated[OpportunityCatalog, Depends(deps.catalog)],
    ) -> CareersService:
        return CareersService(policy, catalog=catalog, clock=deps.clock, **extra)

    def program_service(
        policy: Annotated[DemoCareerPolicy, Depends(deps.policy)],
        uow: Annotated[CareersUnitOfWork, Depends(deps.uow)],
    ) -> CareersService:
        return CareersService(policy, uow=uow, clock=deps.clock, **extra)

    def verified_actor(
        actor: Annotated[CareersActor | None, Depends(deps.actor)],
    ) -> CareersActor:
        # Resolved first, so anonymous calls never reach the unit of work.
        return require_actor(actor)

    def authorized(grant: CareerGrant):
        def check(
            actor: Annotated[CareersActor, Depends(verified_actor)],
            policy: Annotated[DemoCareerPolicy, Depends(deps.policy)],
            uow: Annotated[CareersUnitOfWork, Depends(deps.uow)],
        ) -> tuple[CareersActor, CareersService]:
            # Early 403 before body/header validation; the service re-checks the grant inside
            # the write transaction so a revoked grant is honoured even on replay.
            service = CareersService(policy, uow=uow, clock=deps.clock, **extra)
            with uow.transaction() as tx:
                require_grant(tx.grants(actor.user_id), grant)
            return actor, service

        return check

    Public = Annotated[CareersService, Depends(public_service)]
    Programs = Annotated[CareersService, Depends(program_service)]
    ProfileOwner = Annotated[
        tuple[CareersActor, CareersService], Depends(authorized(CareerGrant.PROFILE_SELF))
    ]
    Applicant = Annotated[
        tuple[CareersActor, CareersService], Depends(authorized(CareerGrant.PROGRAM_APPLY_SELF))
    ]
    Drafter = Annotated[
        tuple[CareersActor, CareersService], Depends(authorized(CareerGrant.EMPLOYER_DRAFT))
    ]

    def created(response: Response, replayed: bool) -> None:
        response.status_code = 200 if replayed else 201
        if replayed:
            response.headers[REPLAY_HEADER] = "true"

    Text = Annotated[str | None, Query(min_length=1, max_length=50)]
    Department = Annotated[
        str | None, Query(min_length=1, max_length=20, pattern=r"^[A-Za-z0-9_-]+$")
    ]
    Limit = Annotated[int, Query(ge=1, le=50)]
    Cursor = Annotated[str | None, Query(max_length=200)]

    # ---- FR-JOB-001 public job search (opportunity catalog, kind=career) ----

    @router.get("/jobs", response_model=SuccessResponse[JobPageData])
    def list_jobs(
        service: Public,
        q: Text = None,
        department: Department = None,
        open_only: bool = False,
        limit: Limit = 20,
        cursor: Cursor = None,
    ):
        return SuccessResponse(
            data=service.list_jobs(
                text=q, department=department, open_only=open_only, limit=limit, cursor=cursor
            )
        )

    @router.get("/jobs/{job_id}", response_model=SuccessResponse[JobSummaryData])
    def get_job(job_id: UUID, service: Public):
        return SuccessResponse(data=service.get_job(job_id))

    # ---- FR-OPP-005 contest candidates for community recruitment ID references ----

    @router.get("/contests", response_model=SuccessResponse[ContestPageData])
    def list_contests(service: Public, q: Text = None, limit: Limit = 20, cursor: Cursor = None):
        return SuccessResponse(data=service.list_contests(text=q, limit=limit, cursor=cursor))

    # ---- FR-JOB-002 virtual career profile ----

    @router.get("/me/profile", response_model=SuccessResponse[ProfileEnvelope])
    def get_profile(owner: ProfileOwner):
        actor, service = owner
        envelope = service.get_profile(actor)
        version = envelope.profile.revision if envelope.profile else None
        return SuccessResponse(data=envelope, resource_version=version)

    @router.post("/me/profile", response_model=SuccessResponse[ProfileData], status_code=201)
    def create_profile(
        owner: ProfileOwner,
        body: ProfileCreate,
        idempotency_key: IdempotencyKey,
        response: Response,
    ):
        actor, service = owner
        profile, replayed = service.create_profile(actor, body, idempotency_key)
        created(response, replayed)
        return SuccessResponse(data=profile, resource_version=profile.revision)

    @router.patch("/me/profile", response_model=SuccessResponse[ProfileData])
    def update_profile(owner: ProfileOwner, body: ProfilePatch, if_match: IfMatch):
        actor, service = owner
        profile = service.update_profile(actor, body, parse_if_match(if_match))
        return SuccessResponse(data=profile, resource_version=profile.revision)

    @router.delete("/me/profile", response_model=SuccessResponse[DeletedData])
    def delete_profile(owner: ProfileOwner, if_match: IfMatch):
        actor, service = owner
        return SuccessResponse(data=service.delete_profile(actor, parse_if_match(if_match)))

    # ---- FR-JOB-003 / FR-OPP-006 virtual program applications ----

    @router.get("/programs", response_model=SuccessResponse[ProgramListData])
    def list_programs(service: Programs):
        return SuccessResponse(data=service.list_programs())

    @router.post(
        "/programs/{program_id}/applications",
        response_model=SuccessResponse[ApplicationData],
        status_code=201,
    )
    def apply(
        program_id: UUID,
        applicant: Applicant,
        body: ApplicationCreate,
        idempotency_key: IdempotencyKey,
        response: Response,
    ):
        actor, service = applicant
        application, replayed = service.apply(actor, program_id, body, idempotency_key)
        created(response, replayed)
        return SuccessResponse(data=application, resource_version=application.revision)

    @router.get("/me/program-applications", response_model=SuccessResponse[ApplicationListData])
    def list_applications(applicant: Applicant):
        actor, service = applicant
        return SuccessResponse(data=service.list_applications(actor))

    @router.get(
        "/me/program-applications/{application_id}",
        response_model=SuccessResponse[ApplicationData],
    )
    def get_application(application_id: UUID, applicant: Applicant):
        actor, service = applicant
        application = service.get_application(actor, application_id)
        return SuccessResponse(data=application, resource_version=application.revision)

    @router.post(
        "/me/program-applications/{application_id}/cancel",
        response_model=SuccessResponse[ApplicationData],
    )
    def cancel_application(
        application_id: UUID,
        applicant: Applicant,
        if_match: IfMatch,
        body: ApplicationCancel | None = None,
    ):
        del body
        actor, service = applicant
        application = service.cancel_application(actor, application_id, parse_if_match(if_match))
        return SuccessResponse(data=application, resource_version=application.revision)

    # ---- FR-JOB-004 employer request drafts (no submission/publication) ----

    @router.get("/employer-requests", response_model=SuccessResponse[EmployerDraftListData])
    def list_employer_drafts(drafter: Drafter):
        actor, service = drafter
        return SuccessResponse(data=service.list_employer_drafts(actor))

    @router.post(
        "/employer-requests", response_model=SuccessResponse[EmployerDraftData], status_code=201
    )
    def create_employer_draft(
        drafter: Drafter,
        body: EmployerDraftCreate,
        idempotency_key: IdempotencyKey,
        response: Response,
    ):
        actor, service = drafter
        draft, replayed = service.create_employer_draft(actor, body, idempotency_key)
        created(response, replayed)
        return SuccessResponse(data=draft, resource_version=draft.revision)

    @router.get("/employer-requests/{draft_id}", response_model=SuccessResponse[EmployerDraftData])
    def get_employer_draft(draft_id: UUID, drafter: Drafter):
        actor, service = drafter
        draft = service.get_employer_draft(actor, draft_id)
        return SuccessResponse(data=draft, resource_version=draft.revision)

    @router.patch(
        "/employer-requests/{draft_id}", response_model=SuccessResponse[EmployerDraftData]
    )
    def update_employer_draft(
        draft_id: UUID, drafter: Drafter, body: EmployerDraftPatch, if_match: IfMatch
    ):
        actor, service = drafter
        draft = service.update_employer_draft(actor, draft_id, body, parse_if_match(if_match))
        return SuccessResponse(data=draft, resource_version=draft.revision)

    @router.delete("/employer-requests/{draft_id}", response_model=SuccessResponse[DeletedData])
    def delete_employer_draft(draft_id: UUID, drafter: Drafter, if_match: IfMatch):
        actor, service = drafter
        return SuccessResponse(
            data=service.delete_employer_draft(actor, draft_id, parse_if_match(if_match))
        )

    return router


# Fail-closed default; root wires create_careers_router(CareersDependencies(...)) after approval.
router = create_careers_router()
