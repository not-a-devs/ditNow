"""Pure API-OPP rules: public filtering, owner-only preparation state and checklist.

Callers pass a verified principal user_id; this module never trusts body/query identity.
"""

import hashlib
import json
from collections.abc import Callable
from dataclasses import replace
from datetime import datetime
from urllib.parse import urlsplit
from uuid import UUID, uuid4

from app.core.errors import ApiError
from app.features.opportunities.repository import (
    CheckRecord,
    OpportunityCatalog,
    OpportunityQuery,
    OpportunityRecord,
    SavedOpportunityStore,
    SavedRecord,
    StatusEvent,
)
from app.features.opportunities.schemas import (
    CheckItemCreate,
    CheckItemData,
    CheckItemPatch,
    OpportunityDetailData,
    OpportunityFileData,
    OpportunityPageData,
    OpportunitySummaryData,
    PreparationStatus,
    PublicationStatus,
    SavedOpportunityData,
    SavedOpportunityPatch,
    SaveOpportunityRequest,
    SourceKind,
    SubmissionMode,
    TargetScopeData,
)
from app.schemas.common import ErrorCode, utc_now

MAX_CHECKS_PER_SAVED = 50
MAX_LIMIT = 50

_S = PreparationStatus
# closed is terminal; deleting the saved row is the reset path.
ALLOWED_TRANSITIONS: dict[PreparationStatus, frozenset[PreparationStatus]] = {
    _S.INTERESTED: frozenset({_S.PREPARING, _S.CLOSED}),
    _S.PREPARING: frozenset({_S.INTERESTED, _S.SELF_REPORTED_SUBMITTED, _S.CLOSED}),
    # Correction of a mistaken self-report is allowed and recorded as a correction event.
    _S.SELF_REPORTED_SUBMITTED: frozenset({_S.PREPARING, _S.CLOSED}),
    _S.CLOSED: frozenset(),
}


def safe_url(value: str | None) -> str | None:
    """Only absolute http(s) URLs leave the API; others (javascript:, data:, relative) drop."""
    if not value:
        return None
    try:
        parts = urlsplit(value)
    except ValueError:
        return None
    if parts.scheme not in {"https", "http"} or not parts.netloc or parts.username:
        return None
    return value


def deadline_passed(record: OpportunityRecord, now: datetime) -> bool:
    return record.deadline_at is not None and record.deadline_at <= now


def matches(record: OpportunityRecord, query: OpportunityQuery, now: datetime) -> bool:
    """Public visibility + user-chosen filters. A department filter narrows display only."""
    if record.status is not PublicationStatus.PUBLISHED:
        return False
    if query.kind is not None and record.kind is not query.kind:
        return False
    if query.open_only and deadline_passed(record, now):
        return False
    if query.department_code is not None:
        scope = record.target_scope
        if scope.level != "school" and query.department_code not in scope.department_codes:
            return False
    if query.text:
        needle = query.text.casefold()
        haystack = f"{record.title}\n{record.organization}".casefold()
        if needle not in haystack:
            return False
    return True


def _needs_verification(record: OpportunityRecord) -> bool:
    return (
        record.source_kind is SourceKind.DEMO
        or safe_url(record.original_url or record.source_url) is None
        or record.checked_at is None
    )


def to_summary(record: OpportunityRecord, now: datetime) -> OpportunitySummaryData:
    return OpportunitySummaryData(
        id=record.id,
        kind=record.kind,
        title=record.title,
        organization=record.organization,
        target_scope=TargetScopeData(
            level=record.target_scope.level,
            department_codes=list(record.target_scope.department_codes),
            academic_years=list(record.target_scope.academic_years),
        ),
        apply_starts_at=record.apply_starts_at,
        deadline_at=record.deadline_at,
        deadline_passed=deadline_passed(record, now),
        submission_mode=record.submission_mode,
        source_kind=record.source_kind,
        needs_verification=_needs_verification(record),
    )


def to_detail(record: OpportunityRecord, now: datetime) -> OpportunityDetailData:
    return OpportunityDetailData(
        **to_summary(record, now).model_dump(),
        eligibility=record.eligibility,
        destination=record.destination,
        original_url=safe_url(record.original_url),
        source_url=safe_url(record.source_url),
        checked_at=record.checked_at,
        files=[
            OpportunityFileData(
                filename=f.filename, original_url=safe_url(f.original_url), checked_at=f.checked_at
            )
            for f in record.files
        ],
    )


def _to_check(record: CheckRecord) -> CheckItemData:
    return CheckItemData(
        id=record.id,
        text=record.text,
        sort_order=record.sort_order,
        completed_at=record.completed_at,
        revision=record.revision,
    )


def _request_hash(body: CheckItemCreate) -> str:
    raw = json.dumps(body.model_dump(mode="json"), sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode()).hexdigest()


class OpportunityService:
    def __init__(
        self,
        catalog: OpportunityCatalog,
        store: SavedOpportunityStore | None = None,
        *,
        clock: Callable[[], datetime] = utc_now,
        id_factory: Callable[[], UUID] = uuid4,
    ):
        self._catalog = catalog
        self._store = store
        self._clock = clock
        self._new_id = id_factory

    # ---- public catalog (FR-OPP-001 read, FR-OPP-003) ----

    def list_public(self, query: OpportunityQuery) -> OpportunityPageData:
        if not 1 <= query.limit <= MAX_LIMIT:
            raise ApiError(ErrorCode.VALIDATION)
        now = self._clock()
        page = self._catalog.list_public(query, now)
        # Defense in depth: drop anything the adapter returned that is not public/matching.
        items = [to_summary(r, now) for r in page.items[: query.limit] if matches(r, query, now)]
        return OpportunityPageData(items=items, next_cursor=page.next_cursor)

    def get_public(self, opportunity_id: UUID) -> OpportunityDetailData:
        return to_detail(self._require_public(opportunity_id), self._clock())

    def _require_public(self, opportunity_id: UUID) -> OpportunityRecord:
        record = self._catalog.get(opportunity_id)
        if record is None or record.status is not PublicationStatus.PUBLISHED:
            raise ApiError(ErrorCode.NOT_FOUND)
        return record

    # ---- owner preparation (FR-OPP-004) ----

    @property
    def _owner_store(self) -> SavedOpportunityStore:
        if self._store is None:
            raise ApiError(ErrorCode.UNAVAILABLE)
        return self._store

    def _require_saved(self, user_id: UUID, opportunity_id: UUID) -> SavedRecord:
        saved = self._owner_store.get(user_id, opportunity_id)
        # Another user's row and a missing row are indistinguishable (404).
        if saved is None or saved.user_id != user_id:
            raise ApiError(ErrorCode.NOT_FOUND)
        return saved

    def _view(self, saved: SavedRecord, now: datetime) -> SavedOpportunityData:
        record = self._catalog.get(saved.opportunity_id)
        visible = record is not None and record.status is PublicationStatus.PUBLISHED
        checks = sorted(self._owner_store.list_checks(saved.id), key=lambda c: c.sort_order)
        return SavedOpportunityData(
            opportunity_id=saved.opportunity_id,
            status=saved.status,
            memo=saved.memo,
            self_reported_submitted_at=saved.self_reported_submitted_at,
            revision=saved.revision,
            created_at=saved.created_at,
            updated_at=saved.updated_at,
            checks=[_to_check(c) for c in checks],
            opportunity=to_summary(record, now) if visible and record else None,
        )

    def list_saved(self, user_id: UUID) -> list[SavedOpportunityData]:
        now = self._clock()
        rows = [r for r in self._owner_store.list_for_user(user_id) if r.user_id == user_id]
        return [self._view(r, now) for r in sorted(rows, key=lambda r: r.created_at)]

    def save(
        self, user_id: UUID, opportunity_id: UUID, body: SaveOpportunityRequest
    ) -> tuple[SavedOpportunityData, bool]:
        """Idempotent PUT: repeated calls return the same row unchanged."""
        self._require_public(opportunity_id)
        now = self._clock()
        candidate = SavedRecord(
            id=self._new_id(),
            user_id=user_id,
            opportunity_id=opportunity_id,
            status=PreparationStatus.INTERESTED,
            memo=body.memo,
            self_reported_submitted_at=None,
            revision=1,
            created_at=now,
            updated_at=now,
        )
        saved, created = self._owner_store.insert_if_absent(candidate)
        if saved.user_id != user_id:
            raise ApiError(ErrorCode.INTERNAL)
        return self._view(saved, now), created

    def update(
        self,
        user_id: UUID,
        opportunity_id: UUID,
        body: SavedOpportunityPatch,
        expected_revision: int,
    ) -> SavedOpportunityData:
        saved = self._require_saved(user_id, opportunity_id)
        if saved.revision != expected_revision:
            raise ApiError(ErrorCode.CONFLICT)
        now = self._clock()
        changed = saved
        if body.memo is not None:
            changed = replace(changed, memo=body.memo)
        event: StatusEvent | None = None
        if body.status is not None and body.status is not saved.status:
            if body.status not in ALLOWED_TRANSITIONS[saved.status]:
                raise ApiError(ErrorCode.CONFLICT)
            if body.status is PreparationStatus.SELF_REPORTED_SUBMITTED:
                record = self._catalog.get(opportunity_id)
                if record is None or record.submission_mode is SubmissionMode.INFO_ONLY:
                    raise ApiError(ErrorCode.CONFLICT)
            if body.status is PreparationStatus.SELF_REPORTED_SUBMITTED:
                submitted_at: datetime | None = now
            elif body.status is PreparationStatus.CLOSED:
                submitted_at = saved.self_reported_submitted_at
            else:
                submitted_at = None
            changed = replace(changed, status=body.status, self_reported_submitted_at=submitted_at)
            event = StatusEvent(
                saved_id=saved.id,
                user_id=user_id,
                from_status=saved.status,
                to_status=body.status,
                occurred_at=now,
                correction=saved.status is PreparationStatus.SELF_REPORTED_SUBMITTED
                and body.status is PreparationStatus.PREPARING,
            )
        if changed == saved:
            return self._view(saved, now)
        changed = replace(changed, revision=saved.revision + 1, updated_at=now)
        if not self._owner_store.compare_and_set(changed, expected_revision):
            raise ApiError(ErrorCode.CONFLICT)
        if event is not None:
            self._owner_store.append_status_event(event)
        return self._view(changed, now)

    def delete(self, user_id: UUID, opportunity_id: UUID, expected_revision: int) -> None:
        saved = self._require_saved(user_id, opportunity_id)
        if saved.revision != expected_revision:
            raise ApiError(ErrorCode.CONFLICT)
        if not self._owner_store.delete_with_checks(user_id, saved.id, expected_revision):
            raise ApiError(ErrorCode.CONFLICT)

    # ---- checklist ----

    def _require_check(self, saved: SavedRecord, check_id: UUID) -> tuple[CheckRecord, list]:
        checks = self._owner_store.list_checks(saved.id)
        found = next((c for c in checks if c.id == check_id and c.saved_id == saved.id), None)
        if found is None:
            raise ApiError(ErrorCode.NOT_FOUND)
        return found, checks

    def add_check(
        self,
        user_id: UUID,
        opportunity_id: UUID,
        body: CheckItemCreate,
        idempotency_key: str,
    ) -> tuple[CheckItemData, bool]:
        saved = self._require_saved(user_id, opportunity_id)
        request_hash = _request_hash(body)
        previous = self._owner_store.find_check_by_idempotency_key(saved.id, idempotency_key)
        if previous is not None:
            record, stored_hash = previous
            if stored_hash != request_hash:
                raise ApiError(ErrorCode.CONFLICT)
            return _to_check(record), False
        checks = self._owner_store.list_checks(saved.id)
        if len(checks) >= MAX_CHECKS_PER_SAVED:
            raise ApiError(ErrorCode.CONFLICT)
        if any(c.sort_order == body.sort_order for c in checks):
            raise ApiError(ErrorCode.CONFLICT)
        record = CheckRecord(
            id=self._new_id(),
            saved_id=saved.id,
            text=body.text,
            sort_order=body.sort_order,
            completed_at=None,
            revision=1,
        )
        self._owner_store.insert_check(record, idempotency_key, request_hash)
        return _to_check(record), True

    def update_check(
        self,
        user_id: UUID,
        opportunity_id: UUID,
        check_id: UUID,
        body: CheckItemPatch,
        expected_revision: int,
    ) -> CheckItemData:
        saved = self._require_saved(user_id, opportunity_id)
        check, checks = self._require_check(saved, check_id)
        if check.revision != expected_revision:
            raise ApiError(ErrorCode.CONFLICT)
        changed = check
        if body.text is not None:
            changed = replace(changed, text=body.text)
        if body.sort_order is not None and body.sort_order != check.sort_order:
            if any(c.sort_order == body.sort_order and c.id != check.id for c in checks):
                raise ApiError(ErrorCode.CONFLICT)
            changed = replace(changed, sort_order=body.sort_order)
        if body.completed is not None and body.completed != (check.completed_at is not None):
            changed = replace(changed, completed_at=self._clock() if body.completed else None)
        if changed == check:
            return _to_check(check)
        changed = replace(changed, revision=check.revision + 1)
        if not self._owner_store.compare_and_set_check(changed, expected_revision):
            raise ApiError(ErrorCode.CONFLICT)
        return _to_check(changed)

    def delete_check(
        self, user_id: UUID, opportunity_id: UUID, check_id: UUID, expected_revision: int
    ) -> None:
        saved = self._require_saved(user_id, opportunity_id)
        check, _ = self._require_check(saved, check_id)
        if check.revision != expected_revision:
            raise ApiError(ErrorCode.CONFLICT)
        if not self._owner_store.delete_check(saved.id, check_id, expected_revision):
            raise ApiError(ErrorCode.CONFLICT)
