"""Owner-scoped SQLAlchemy adapters for the existing opportunity Protocols."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.db.models import (
    CheckClaimRow,
    OpportunityCheckItemRow,
    OpportunityRow,
    SavedOpportunityRow,
    SavedStatusEventRow,
)
from app.features.opportunities.repository import (
    CheckRecord,
    IdempotencyEntry,
    IdempotencyScope,
    OpportunityFile,
    OpportunityPage,
    OpportunityQuery,
    OpportunityRecord,
    SavedRecord,
    StatusEvent,
    StoreConflict,
    TargetScope,
    source_kind_from_storage,
)
from app.features.opportunities.schemas import (
    OpportunityFileData,
    OpportunityKind,
    PreparationStatus,
    PublicationStatus,
    SubmissionMode,
    TargetScopeData,
)
from app.features.opportunities.service import MAX_CHECKS_PER_SAVED, matches
from app.repositories.community_sql import namespace_digest
from app.repositories.p0_access import CurrentP0Access
from app.schemas.common import ErrorCode


def opportunity(row: OpportunityRow) -> OpportunityRecord | None:
    try:
        scope = TargetScopeData.model_validate(row.target_scope)
        files = [
            OpportunityFileData.model_validate(
                {
                    "filename": f["filename"],
                    "original_url": f.get("original_url"),
                    "checked_at": f.get("checked_at"),
                }
            )
            for f in row.files
        ]
        return OpportunityRecord(
            id=row.id,
            kind=OpportunityKind(row.kind),
            title=row.title,
            organization=row.organization,
            eligibility=row.eligibility,
            submission_mode=SubmissionMode(row.submission_mode),
            source_kind=source_kind_from_storage(row.source_kind),
            status=PublicationStatus(row.status),
            target_scope=TargetScope(
                scope.level,
                tuple(scope.department_codes),
                tuple(scope.academic_years),
            ),
            apply_starts_at=row.apply_starts_at,
            deadline_at=row.deadline_at,
            destination=row.destination,
            original_url=row.original_url,
            source_url=row.source_url,
            checked_at=row.checked_at,
            files=tuple(
                OpportunityFile(
                    f.filename,
                    f.original_url,
                    f.checked_at,
                )
                for f in files
            ),
        )
    except (ValueError, TypeError, KeyError, AttributeError):
        # An incompatible legacy/unapproved catalog row never becomes a public result.
        return None


class SQLOpportunityCatalog:
    def __init__(self, session: Session):
        self.session = session

    def get(self, opportunity_id: UUID):
        row = self.session.get(OpportunityRow, opportunity_id, populate_existing=True)
        return opportunity(row) if row is not None else None

    def list_public(self, query: OpportunityQuery, now: datetime):
        statement = select(OpportunityRow).where(
            OpportunityRow.status == "published",
            OpportunityRow.source_kind.in_(
                ["OFFICIAL_PUBLIC", "DEMO", "official_public", "synthetic_demo"]
            ),
        )
        if query.kind is not None:
            statement = statement.where(OpportunityRow.kind == query.kind.value)
        if query.open_only:
            statement = statement.where(
                (OpportunityRow.deadline_at.is_(None)) | (OpportunityRow.deadline_at > now)
            )
        if query.cursor is not None:
            try:
                after = UUID(query.cursor)
            except ValueError:
                raise ApiError(ErrorCode.VALIDATION) from None
            statement = statement.where(OpportunityRow.id > after)
        rows = list(
            self.session.scalars(statement.order_by(OpportunityRow.id).limit(query.limit + 1))
        )
        scanned = rows[: query.limit]
        records = [
            r for row in scanned if (r := opportunity(row)) is not None and matches(r, query, now)
        ]
        cursor = str(scanned[-1].id) if scanned and len(rows) > query.limit else None
        return OpportunityPage(records, cursor)

    def is_linkable(self, actor_id: str, opportunity_id: str):
        try:
            id = UUID(opportunity_id)
        except ValueError:
            return False
        record = self.get(id)
        return record is not None and record.status is PublicationStatus.PUBLISHED


def saved(row: SavedOpportunityRow) -> SavedRecord:
    return SavedRecord(
        row.id,
        row.user_id,
        row.opportunity_id,
        PreparationStatus(row.status),
        row.memo,
        row.self_reported_submitted_at,
        row.revision,
        row.created_at,
        row.updated_at,
    )


def check(row: OpportunityCheckItemRow) -> CheckRecord:
    return CheckRecord(
        row.id, row.saved_opportunity_id, row.text, row.sort_order, row.completed_at, row.revision
    )


class SQLSavedOpportunities:
    def __init__(self, session: Session, access: CurrentP0Access):
        self.session, self.access = session, access

    def _actor(self):
        return self.access.require()

    def _parent(self, saved_id: UUID):
        actor = self._actor()
        row = self.session.scalar(
            select(SavedOpportunityRow)
            .where(SavedOpportunityRow.id == saved_id, SavedOpportunityRow.user_id == actor)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if row is None:
            raise ApiError(ErrorCode.NOT_FOUND)
        return row

    def get(self, user_id: UUID, opportunity_id: UUID):
        if user_id != self._actor():
            return None
        row = self.session.scalar(
            select(SavedOpportunityRow)
            .where(
                SavedOpportunityRow.user_id == user_id,
                SavedOpportunityRow.opportunity_id == opportunity_id,
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        return saved(row) if row else None

    def list_for_user(self, user_id: UUID):
        if user_id != self._actor():
            return []
        return [
            saved(row)
            for row in self.session.scalars(
                select(SavedOpportunityRow)
                .where(SavedOpportunityRow.user_id == user_id)
                .order_by(SavedOpportunityRow.created_at, SavedOpportunityRow.id)
            )
        ]

    def insert_if_absent(self, record: SavedRecord):
        if record.user_id != self._actor():
            raise ApiError(ErrorCode.NOT_FOUND)
        existing = self.get(record.user_id, record.opportunity_id)
        if existing:
            return existing, False
        try:
            with self.session.begin_nested():
                self.session.add(
                    SavedOpportunityRow(
                        id=record.id,
                        user_id=record.user_id,
                        opportunity_id=record.opportunity_id,
                        status=record.status.value,
                        memo=record.memo,
                        self_reported_submitted_at=record.self_reported_submitted_at,
                        revision=record.revision,
                        created_at=record.created_at,
                        updated_at=record.updated_at,
                        source_kind="USER_DEMO",
                    )
                )
                self.session.flush()
        except IntegrityError:
            existing = self.get(record.user_id, record.opportunity_id)
            if existing is None:
                raise StoreConflict() from None
            return existing, False
        return record, True

    def compare_and_set(
        self, record: SavedRecord, expected_revision: int, event: StatusEvent | None
    ):
        if record.user_id != self._actor() or record.revision != expected_revision + 1:
            return False
        self._parent(record.id)
        result = self.session.execute(
            update(SavedOpportunityRow)
            .where(
                SavedOpportunityRow.id == record.id,
                SavedOpportunityRow.user_id == record.user_id,
                SavedOpportunityRow.revision == expected_revision,
            )
            .values(
                status=record.status.value,
                memo=record.memo,
                self_reported_submitted_at=record.self_reported_submitted_at,
                revision=record.revision,
                updated_at=record.updated_at,
            )
            .execution_options(synchronize_session=False)
        )
        if result.rowcount != 1:
            return False
        if event is not None:
            if event.user_id != record.user_id or event.saved_id != record.id:
                raise ApiError(ErrorCode.INTERNAL)
            self.session.add(
                SavedStatusEventRow(
                    saved_id=event.saved_id,
                    user_id=event.user_id,
                    from_status=event.from_status.value,
                    to_status=event.to_status.value,
                    occurred_at=event.occurred_at,
                    correction=event.correction,
                )
            )
        self.session.flush()
        self.session.expire_all()
        return True

    def delete_with_checks(self, user_id: UUID, saved_id: UUID, expected_revision: int):
        if user_id != self._actor():
            return False
        row = self._parent(saved_id)
        if row.revision != expected_revision:
            return False
        self.session.execute(
            update(CheckClaimRow)
            .where(CheckClaimRow.actor_id == user_id, CheckClaimRow.original_saved_id == saved_id)
            .values(tombstone=True)
        )
        self.session.execute(
            delete(OpportunityCheckItemRow).where(
                OpportunityCheckItemRow.saved_opportunity_id == saved_id
            )
        )
        self.session.delete(row)
        self.session.flush()
        return True

    def list_checks(self, saved_id: UUID):
        self._parent(saved_id)
        return [
            check(row)
            for row in self.session.scalars(
                select(OpportunityCheckItemRow)
                .where(OpportunityCheckItemRow.saved_opportunity_id == saved_id)
                .order_by(OpportunityCheckItemRow.sort_order)
            )
        ]

    def _digest(self, scope: IdempotencyScope):
        if scope.user_id != self._actor():
            raise ApiError(ErrorCode.NOT_FOUND)
        return namespace_digest(
            [str(scope.user_id), str(scope.opportunity_id), scope.operation, scope.key]
        )

    def find_idempotency(self, scope: IdempotencyScope):
        row = self.session.scalar(
            select(CheckClaimRow)
            .where(CheckClaimRow.namespace_digest == self._digest(scope))
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if row is None:
            return None
        if (row.actor_id, row.opportunity_id, row.operation, row.key) != (
            scope.user_id,
            scope.opportunity_id,
            scope.operation,
            scope.key,
        ):
            raise ApiError(ErrorCode.INTERNAL)
        item = (
            None
            if row.tombstone
            else self.session.get(OpportunityCheckItemRow, row.check_id, populate_existing=True)
        )
        if item is not None and item.saved_opportunity_id != row.original_saved_id:
            raise ApiError(ErrorCode.INTERNAL)
        return IdempotencyEntry(
            scope, row.request_hash, row.check_id, check(item) if item else None
        )

    def insert_check(self, record: CheckRecord, scope: IdempotencyScope, request_hash: str):
        parent = self._parent(record.saved_id)
        if parent.opportunity_id != scope.opportunity_id or scope.user_id != parent.user_id:
            raise StoreConflict()
        previous = self.find_idempotency(scope)
        if previous:
            return previous
        count = self.session.scalar(
            select(func.count())
            .select_from(OpportunityCheckItemRow)
            .where(OpportunityCheckItemRow.saved_opportunity_id == record.saved_id)
        )
        if count >= MAX_CHECKS_PER_SAVED:
            raise StoreConflict()
        try:
            with self.session.begin_nested():
                self.session.add(
                    CheckClaimRow(
                        namespace_digest=self._digest(scope),
                        actor_id=scope.user_id,
                        opportunity_id=scope.opportunity_id,
                        operation=scope.operation,
                        key=scope.key,
                        request_hash=request_hash,
                        check_id=record.id,
                        original_saved_id=record.saved_id,
                        tombstone=False,
                    )
                )
                self.session.add(
                    OpportunityCheckItemRow(
                        id=record.id,
                        saved_opportunity_id=record.saved_id,
                        text=record.text,
                        sort_order=record.sort_order,
                        completed_at=record.completed_at,
                        revision=record.revision,
                        source_kind="USER_DEMO",
                    )
                )
                self.session.flush()
        except IntegrityError:
            previous = self.find_idempotency(scope)
            if previous is not None:
                return previous
            raise StoreConflict() from None
        return IdempotencyEntry(scope, request_hash, record.id, record)

    def compare_and_set_check(self, record: CheckRecord, expected_revision: int):
        self._parent(record.saved_id)
        if record.revision != expected_revision + 1:
            return False
        try:
            with self.session.begin_nested():
                result = self.session.execute(
                    update(OpportunityCheckItemRow)
                    .where(
                        OpportunityCheckItemRow.id == record.id,
                        OpportunityCheckItemRow.saved_opportunity_id == record.saved_id,
                        OpportunityCheckItemRow.revision == expected_revision,
                    )
                    .values(
                        text=record.text,
                        sort_order=record.sort_order,
                        completed_at=record.completed_at,
                        revision=record.revision,
                    )
                    .execution_options(synchronize_session=False)
                )
                self.session.flush()
        except IntegrityError:
            return False
        self.session.expire_all()
        return result.rowcount == 1

    def delete_check(self, saved_id: UUID, check_id: UUID, expected_revision: int):
        parent = self._parent(saved_id)
        result = self.session.execute(
            delete(OpportunityCheckItemRow).where(
                OpportunityCheckItemRow.id == check_id,
                OpportunityCheckItemRow.saved_opportunity_id == saved_id,
                OpportunityCheckItemRow.revision == expected_revision,
            )
        )
        if result.rowcount != 1:
            return False
        self.session.execute(
            update(CheckClaimRow)
            .where(
                CheckClaimRow.actor_id == parent.user_id,
                CheckClaimRow.original_saved_id == saved_id,
                CheckClaimRow.check_id == check_id,
            )
            .values(tombstone=True)
        )
        self.session.flush()
        return True
