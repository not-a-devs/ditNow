"""API-JOB service. Callers pass a server-verified `CareersActor`; identity never comes from the
body or query. Order on every protected call: actor (401) -> current grant in the same
transaction (403) -> owner-scoped lookup (404, other users' rows look missing) -> revision/state
(409). Idempotent creates key on actor+method+canonical path+key and store a payload hash.
"""

import hashlib
import json
from collections.abc import Callable
from dataclasses import replace
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from app.core.errors import ApiError
from app.features.careers.domain import (
    ApplicationStatus,
    CareerGrant,
    CareersActor,
    DemoCareerPolicy,
    Provenance,
    ensure_utc,
    require_actor,
    require_grant,
    resolve_provenance,
    safe_external_url,
    window_open,
)
from app.features.careers.linking import contest_linkable
from app.features.careers.ports import (
    ApplicationRecord,
    CareersTransaction,
    CareersUnitOfWork,
    ClaimScope,
    EmployerDraftRecord,
    IdempotencyClaim,
    ProfileRecord,
    ProgramRecord,
    ResourceType,
    StoreConflict,
)
from app.features.careers.schemas import (
    ApplicationCreate,
    ApplicationData,
    ApplicationListData,
    ContestCandidateData,
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
    ProgramData,
    ProgramListData,
)
from app.features.opportunities.repository import OpportunityCatalog, OpportunityQuery
from app.features.opportunities.schemas import OpportunityKind, PublicationStatus, SourceKind
from app.features.opportunities.service import deadline_passed, matches
from app.schemas.common import ErrorCode, utc_now

MAX_LIMIT = 50
PROFILE_PATH = "/careers/me/profile"
EMPLOYER_PATH = "/careers/employer-requests"


def program_applications_path(program_id: UUID) -> str:
    return f"/careers/programs/{program_id}/applications"


def payload_hash(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _conflict() -> ApiError:
    return ApiError(ErrorCode.CONFLICT)


class CareersService:
    def __init__(
        self,
        policy: DemoCareerPolicy,
        *,
        catalog: OpportunityCatalog | None = None,
        uow: CareersUnitOfWork | None = None,
        clock: Callable[[], datetime] = utc_now,
        id_factory: Callable[[], UUID] = uuid4,
    ):
        if policy.basis != "DEMO":
            raise ApiError(ErrorCode.UNAVAILABLE)
        self._policy = policy
        self._catalog = catalog
        self._uow = uow
        self._clock = clock
        self._new_id = id_factory

    def _now(self) -> datetime:
        now = ensure_utc(self._clock())
        if now is None:
            raise ApiError(ErrorCode.INTERNAL)
        return now

    def _require_catalog(self) -> OpportunityCatalog:
        if self._catalog is None:
            raise ApiError(ErrorCode.UNAVAILABLE)
        return self._catalog

    def _tx(self):
        if self._uow is None:
            raise ApiError(ErrorCode.UNAVAILABLE)
        return self._uow.transaction()

    # ------------------------------------------------ FR-JOB-001 public job search

    def _job(self, record, now: datetime) -> JobSummaryData | None:
        try:
            starts, deadline = ensure_utc(record.apply_starts_at), ensure_utc(record.deadline_at)
            checked = ensure_utc(record.checked_at)
        except ValueError:
            return None  # adapter returned a naive datetime: drop rather than guess the zone
        url = record.original_url or record.source_url
        return JobSummaryData(
            id=record.id,
            title=record.title,
            organization=record.organization,
            department_codes=list(record.target_scope.department_codes),
            apply_starts_at=starts,
            deadline_at=deadline,
            deadline_passed=deadline_passed(record, now),
            provenance=resolve_provenance(
                record.source_kind is SourceKind.OFFICIAL_PUBLIC, url, checked
            ),
            original_url=safe_external_url(url),
            checked_at=checked,
        )

    def _query(self, kind: OpportunityKind, text, department, open_only, limit, cursor):
        if not 1 <= limit <= MAX_LIMIT:
            raise ApiError(ErrorCode.VALIDATION)
        return OpportunityQuery(
            kind=kind,
            text=text.strip() if text and text.strip() else None,
            department_code=department,
            open_only=open_only,
            limit=limit,
            cursor=cursor,
        )

    def list_jobs(
        self,
        *,
        text: str | None = None,
        department: str | None = None,
        open_only: bool = False,
        limit: int = 20,
        cursor: str | None = None,
    ) -> JobPageData:
        """Reuses the approved opportunity catalog (kind=career); no separate job ledger."""
        query = self._query(OpportunityKind.CAREER, text, department, open_only, limit, cursor)
        now = self._now()
        page = self._require_catalog().list_public(query, now)
        items = [
            job
            for record in page.items[:limit]
            # Defense in depth: never trust the adapter to have filtered kind/visibility.
            if matches(record, query, now) and (job := self._job(record, now)) is not None
        ]
        return JobPageData(items=items, next_cursor=page.next_cursor)

    def get_job(self, job_id: UUID) -> JobSummaryData:
        record = self._require_catalog().get(job_id)
        if (
            record is None
            or record.status is not PublicationStatus.PUBLISHED
            or record.kind is not OpportunityKind.CAREER
        ):
            raise ApiError(ErrorCode.NOT_FOUND)
        job = self._job(record, self._now())
        if job is None:
            raise ApiError(ErrorCode.NOT_FOUND)
        return job

    # ------------------------------------------------ FR-OPP-005 contest -> team link candidates

    def list_contests(
        self, *, text: str | None = None, limit: int = 20, cursor: str | None = None
    ) -> ContestPageData:
        query = self._query(OpportunityKind.CONTEST, text, None, False, limit, cursor)
        now = self._now()
        page = self._require_catalog().list_public(query, now)
        items: list[ContestCandidateData] = []
        for record in page.items[:limit]:
            if not matches(record, query, now) or (job := self._job(record, now)) is None:
                continue
            items.append(
                ContestCandidateData(
                    opportunity_id=record.id,
                    title=job.title,
                    organization=job.organization,
                    deadline_at=job.deadline_at,
                    provenance=job.provenance,
                    original_url=job.original_url,
                    checked_at=job.checked_at,
                    team_link_candidate=contest_linkable(record, self._policy, now),
                )
            )
        return ContestPageData(items=items, next_cursor=page.next_cursor)

    # ------------------------------------------------ shared idempotency helpers

    def _authorized(self, tx: CareersTransaction, actor: CareersActor, grant: CareerGrant):
        require_grant(tx.grants(actor.user_id), grant)

    @staticmethod
    def _claim_target(
        claim: IdempotencyClaim, scope: ClaimScope, digest: str, kind: ResourceType
    ) -> UUID:
        if claim.scope != scope:
            # An adapter returning another scope's claim would leak across actors.
            raise ApiError(ErrorCode.INTERNAL)
        if claim.payload_hash != digest or claim.resource_type != kind:
            raise _conflict()
        return claim.resource_id

    def _idempotent(self, attempt: Callable[[], Any]) -> Any:
        """Run `attempt` (one transaction). A UNIQUE race reruns it once so the loser replays."""
        try:
            return attempt()
        except StoreConflict:
            pass
        try:
            return attempt()
        except StoreConflict:
            raise _conflict() from None

    # ------------------------------------------------ FR-JOB-002 virtual career profile

    @staticmethod
    def _profile(record: ProfileRecord) -> ProfileData:
        return ProfileData(
            id=record.id,
            alias=record.alias,
            desired_roles=list(record.desired_roles),
            skills=list(record.skills),
            summary=record.summary,
            revision=record.revision,
            created_at=record.created_at,
            updated_at=record.updated_at,
        )

    @staticmethod
    def _own_profile(tx: CareersTransaction, actor: CareersActor) -> ProfileRecord:
        record = tx.get_profile(actor.user_id)
        if record is None or record.user_id != actor.user_id:
            raise ApiError(ErrorCode.NOT_FOUND)
        return record

    def get_profile(self, actor: CareersActor | None) -> ProfileEnvelope:
        actor = require_actor(actor)
        with self._tx() as tx:
            self._authorized(tx, actor, CareerGrant.PROFILE_SELF)
            record = tx.get_profile(actor.user_id)
            if record is not None and record.user_id != actor.user_id:
                raise ApiError(ErrorCode.INTERNAL)
            return ProfileEnvelope(profile=self._profile(record) if record else None)

    def create_profile(
        self, actor: CareersActor | None, body: ProfileCreate, key: str
    ) -> tuple[ProfileData, bool]:
        actor = require_actor(actor)
        scope = ClaimScope(actor.user_id, "POST", PROFILE_PATH, key)
        digest = payload_hash(body.model_dump(mode="json"))

        def attempt() -> tuple[ProfileData, bool]:
            with self._tx() as tx:
                self._authorized(tx, actor, CareerGrant.PROFILE_SELF)
                claim = tx.find_claim(scope)
                if claim is not None:
                    target = self._claim_target(claim, scope, digest, "profile")
                    existing = tx.get_profile_by_id(target)
                    if existing is None or existing.user_id != actor.user_id:
                        raise _conflict()  # tombstone: deleted profiles are not resurrected
                    return self._profile(existing), True
                if tx.get_profile(actor.user_id) is not None:
                    raise _conflict()
                now = self._now()
                record = ProfileRecord(
                    id=self._new_id(),
                    user_id=actor.user_id,
                    alias=body.alias,
                    desired_roles=tuple(body.desired_roles),
                    skills=tuple(body.skills),
                    summary=body.summary,
                    revision=1,
                    created_at=now,
                    updated_at=now,
                )
                tx.insert_profile(record)
                tx.put_claim(IdempotencyClaim(scope, digest, "profile", record.id))
                return self._profile(record), False

        return self._idempotent(attempt)

    def update_profile(
        self, actor: CareersActor | None, body: ProfilePatch, expected_revision: int
    ) -> ProfileData:
        actor = require_actor(actor)
        with self._tx() as tx:
            self._authorized(tx, actor, CareerGrant.PROFILE_SELF)
            current = self._own_profile(tx, actor)
            if current.revision != expected_revision:
                raise _conflict()
            changes = body.model_dump(exclude_none=True)
            for name in ("desired_roles", "skills"):
                if name in changes:
                    changes[name] = tuple(changes[name])
            changed = replace(current, **changes)
            if changed == current:
                return self._profile(current)
            changed = replace(changed, revision=current.revision + 1, updated_at=self._now())
            if not tx.update_profile(changed, expected_revision):
                raise _conflict()
            return self._profile(changed)

    def delete_profile(self, actor: CareersActor | None, expected_revision: int) -> DeletedData:
        actor = require_actor(actor)
        with self._tx() as tx:
            self._authorized(tx, actor, CareerGrant.PROFILE_SELF)
            current = self._own_profile(tx, actor)
            if current.revision != expected_revision:
                raise _conflict()
            if not tx.delete_profile(actor.user_id, current.id, expected_revision):
                raise _conflict()
            return DeletedData(id=current.id)

    # ------------------------------------------------ FR-JOB-003 / FR-OPP-006 programs

    def _program(self, record: ProgramRecord, now: datetime) -> ProgramData | None:
        try:
            starts, ends = ensure_utc(record.apply_starts_at), ensure_utc(record.apply_ends_at)
            checked = ensure_utc(record.checked_at)
        except ValueError:
            return None
        provenance = resolve_provenance(record.official, record.source_url, checked)
        return ProgramData(
            id=record.id,
            title=record.title,
            host=record.host,
            summary=record.summary,
            capacity=record.capacity,
            apply_starts_at=starts,
            apply_ends_at=ends,
            window_open=window_open(starts, ends, now),
            provenance=provenance,
            source_url=safe_external_url(record.source_url),
            checked_at=checked,
            accepts_virtual_application=provenance is Provenance.DEMO and record.published,
        )

    def list_programs(self) -> ProgramListData:
        now = self._now()
        with self._tx() as tx:
            rows = [r for r in tx.list_programs() if r.published]
        items = [p for r in rows if (p := self._program(r, now)) is not None]
        return ProgramListData(items=items, policy_id=self._policy.policy_id)

    def _application(
        self, tx: CareersTransaction, record: ApplicationRecord, now: datetime
    ) -> ApplicationData:
        program = tx.get_program(record.program_id)
        view = self._program(program, now) if program is not None and program.published else None
        return ApplicationData(
            id=record.id,
            program_id=record.program_id,
            status=record.status,
            note=record.note,
            revision=record.revision,
            created_at=record.created_at,
            updated_at=record.updated_at,
            cancelled_at=record.cancelled_at,
            program=view,
        )

    @staticmethod
    def _own_application(
        tx: CareersTransaction, actor: CareersActor, application_id: UUID
    ) -> ApplicationRecord:
        record = tx.get_application(application_id)
        if record is None or record.user_id != actor.user_id:
            raise ApiError(ErrorCode.NOT_FOUND)
        return record

    def apply(
        self, actor: CareersActor | None, program_id: UUID, body: ApplicationCreate, key: str
    ) -> tuple[ApplicationData, bool]:
        actor = require_actor(actor)
        scope = ClaimScope(actor.user_id, "POST", program_applications_path(program_id), key)
        digest = payload_hash(body.model_dump(mode="json"))
        policy = self._policy

        def attempt() -> tuple[ApplicationData, bool]:
            with self._tx() as tx:
                self._authorized(tx, actor, CareerGrant.PROGRAM_APPLY_SELF)
                now = self._now()
                claim = tx.find_claim(scope)
                if claim is not None:
                    target = self._claim_target(claim, scope, digest, "program_application")
                    existing = tx.get_application(target)
                    if existing is None or existing.user_id != actor.user_id:
                        raise _conflict()
                    # Replays report the *current* state (e.g. cancelled), never a stale success.
                    return self._application(tx, existing, now), True
                program = tx.lock_program(program_id)
                if program is None or not program.published:
                    raise ApiError(ErrorCode.NOT_FOUND)
                view = self._program(program, now)
                if view is None or not view.accepts_virtual_application:
                    raise _conflict()  # official/unknown programs are information only
                if policy.enforce_program_window and not view.window_open:
                    raise _conflict()
                if tx.find_active_application(actor.user_id, program_id) is not None:
                    raise _conflict()
                if tx.count_active_for_user(actor.user_id) >= (
                    policy.max_active_applications_per_user
                ):
                    raise _conflict()
                if program.capacity is not None and (
                    tx.count_active_for_program(program_id) >= program.capacity
                ):
                    raise _conflict()
                record = ApplicationRecord(
                    id=self._new_id(),
                    user_id=actor.user_id,
                    program_id=program_id,
                    status=ApplicationStatus.APPLIED,
                    note=body.note,
                    revision=1,
                    created_at=now,
                    updated_at=now,
                )
                tx.insert_application(record)
                tx.put_claim(IdempotencyClaim(scope, digest, "program_application", record.id))
                return self._application(tx, record, now), False

        return self._idempotent(attempt)

    def list_applications(self, actor: CareersActor | None) -> ApplicationListData:
        actor = require_actor(actor)
        with self._tx() as tx:
            self._authorized(tx, actor, CareerGrant.PROGRAM_APPLY_SELF)
            now = self._now()
            rows = [r for r in tx.list_applications(actor.user_id) if r.user_id == actor.user_id]
            rows.sort(key=lambda r: r.created_at)
            return ApplicationListData(items=[self._application(tx, r, now) for r in rows])

    def get_application(self, actor: CareersActor | None, application_id: UUID) -> ApplicationData:
        actor = require_actor(actor)
        with self._tx() as tx:
            self._authorized(tx, actor, CareerGrant.PROGRAM_APPLY_SELF)
            record = self._own_application(tx, actor, application_id)
            return self._application(tx, record, self._now())

    def cancel_application(
        self, actor: CareersActor | None, application_id: UUID, expected_revision: int
    ) -> ApplicationData:
        actor = require_actor(actor)
        with self._tx() as tx:
            self._authorized(tx, actor, CareerGrant.PROGRAM_APPLY_SELF)
            current = self._own_application(tx, actor, application_id)
            if current.revision != expected_revision:
                raise _conflict()
            if current.status is not ApplicationStatus.APPLIED:
                raise _conflict()
            now = self._now()
            if not self._policy.allow_cancel_after_window:
                program = tx.get_program(current.program_id)
                view = self._program(program, now) if program else None
                if view is None or not view.window_open:
                    raise _conflict()
            changed = replace(
                current,
                status=ApplicationStatus.CANCELLED,
                cancelled_at=now,
                updated_at=now,
                revision=current.revision + 1,
            )
            if not tx.update_application(changed, expected_revision):
                raise _conflict()
            return self._application(tx, changed, now)

    # ------------------------------------------------ FR-JOB-004 employer request drafts

    @staticmethod
    def _draft(record: EmployerDraftRecord) -> EmployerDraftData:
        return EmployerDraftData(
            id=record.id,
            company_alias=record.company_alias,
            role_title=record.role_title,
            description=record.description,
            employment_type=record.employment_type,
            closes_at=record.closes_at,
            revision=record.revision,
            created_at=record.created_at,
            updated_at=record.updated_at,
        )

    @staticmethod
    def _own_draft(
        tx: CareersTransaction, actor: CareersActor, draft_id: UUID
    ) -> EmployerDraftRecord:
        record = tx.get_employer_draft(draft_id)
        if record is None or record.owner_id != actor.user_id:
            raise ApiError(ErrorCode.NOT_FOUND)
        return record

    def _future_utc(self, value: datetime, now: datetime) -> datetime:
        closes = ensure_utc(value)
        if closes is None or closes <= now:
            raise ApiError(ErrorCode.VALIDATION)
        return closes

    def create_employer_draft(
        self, actor: CareersActor | None, body: EmployerDraftCreate, key: str
    ) -> tuple[EmployerDraftData, bool]:
        actor = require_actor(actor)
        scope = ClaimScope(actor.user_id, "POST", EMPLOYER_PATH, key)
        digest = payload_hash(body.model_dump(mode="json"))

        def attempt() -> tuple[EmployerDraftData, bool]:
            with self._tx() as tx:
                self._authorized(tx, actor, CareerGrant.EMPLOYER_DRAFT)
                claim = tx.find_claim(scope)
                if claim is not None:
                    target = self._claim_target(claim, scope, digest, "employer_request")
                    existing = tx.get_employer_draft(target)
                    if existing is None or existing.owner_id != actor.user_id:
                        raise _conflict()
                    return self._draft(existing), True
                now = self._now()
                closes = self._future_utc(body.closes_at, now)
                if len(tx.list_employer_drafts(actor.user_id)) >= (
                    self._policy.max_employer_drafts_per_actor
                ):
                    raise _conflict()
                record = EmployerDraftRecord(
                    id=self._new_id(),
                    owner_id=actor.user_id,
                    company_alias=body.company_alias,
                    role_title=body.role_title,
                    description=body.description,
                    employment_type=body.employment_type,
                    closes_at=closes,
                    revision=1,
                    created_at=now,
                    updated_at=now,
                )
                tx.insert_employer_draft(record)
                tx.put_claim(IdempotencyClaim(scope, digest, "employer_request", record.id))
                return self._draft(record), False

        return self._idempotent(attempt)

    def list_employer_drafts(self, actor: CareersActor | None) -> EmployerDraftListData:
        actor = require_actor(actor)
        with self._tx() as tx:
            self._authorized(tx, actor, CareerGrant.EMPLOYER_DRAFT)
            rows = [
                r for r in tx.list_employer_drafts(actor.user_id) if r.owner_id == actor.user_id
            ]
            rows.sort(key=lambda r: r.created_at)
            return EmployerDraftListData(items=[self._draft(r) for r in rows])

    def get_employer_draft(self, actor: CareersActor | None, draft_id: UUID) -> EmployerDraftData:
        actor = require_actor(actor)
        with self._tx() as tx:
            self._authorized(tx, actor, CareerGrant.EMPLOYER_DRAFT)
            return self._draft(self._own_draft(tx, actor, draft_id))

    def update_employer_draft(
        self,
        actor: CareersActor | None,
        draft_id: UUID,
        body: EmployerDraftPatch,
        expected_revision: int,
    ) -> EmployerDraftData:
        actor = require_actor(actor)
        with self._tx() as tx:
            self._authorized(tx, actor, CareerGrant.EMPLOYER_DRAFT)
            current = self._own_draft(tx, actor, draft_id)
            if current.revision != expected_revision:
                raise _conflict()
            changes = body.model_dump(exclude_none=True)
            now = self._now()
            if body.closes_at is not None:
                changes["closes_at"] = self._future_utc(body.closes_at, now)
            changed = replace(current, **changes)
            if changed == current:
                return self._draft(current)
            changed = replace(changed, revision=current.revision + 1, updated_at=now)
            if not tx.update_employer_draft(changed, expected_revision):
                raise _conflict()
            return self._draft(changed)

    def delete_employer_draft(
        self, actor: CareersActor | None, draft_id: UUID, expected_revision: int
    ) -> DeletedData:
        actor = require_actor(actor)
        with self._tx() as tx:
            self._authorized(tx, actor, CareerGrant.EMPLOYER_DRAFT)
            current = self._own_draft(tx, actor, draft_id)
            if current.revision != expected_revision:
                raise _conflict()
            if not tx.delete_employer_draft(actor.user_id, draft_id, expected_revision):
                raise _conflict()
            return DeletedData(id=current.id)
