import hashlib
import json
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from uuid import UUID

from app.core.errors import ApiError
from app.features.library.models import (
    BookingView,
    CatalogPage,
    LibraryActor,
    LibraryOverview,
    LibraryPolicy,
    LoanView,
    RevisionInput,
    WishInput,
    WishView,
)
from app.features.library.ports import LibraryStore, LibraryTransaction
from app.schemas.common import ApiModel, ErrorCode


def payload_hash(body: ApiModel) -> str:
    encoded = json.dumps(body.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode()).hexdigest()


class LibraryService:
    def __init__(
        self, store: LibraryStore, clock: Callable[[], datetime] = lambda: datetime.now(UTC)
    ):
        self.store, self.clock = store, clock

    def _now(self):
        value = self.clock()
        if value.tzinfo is None or value.utcoffset() is None:
            raise ApiError(ErrorCode.UNAVAILABLE)
        return value.astimezone(UTC)

    @staticmethod
    def _grant(tx: LibraryTransaction, write: bool = False):
        if not isinstance(getattr(tx, "policy", None), LibraryPolicy):
            raise ApiError(ErrorCode.UNAVAILABLE)
        if not tx.grant.active or (write and not tx.grant.eligible):
            raise ApiError(ErrorCode.FORBIDDEN)

    @staticmethod
    def _owned(row, actor: LibraryActor):
        if row is None or row.owner_id != actor.user_id:
            raise ApiError(ErrorCode.NOT_FOUND)
        return row

    @staticmethod
    def _view(row, model):
        return model(**row.model_dump(exclude={"owner_id"}))

    def catalog(self, query: str, offset: int, limit: int) -> CatalogPage:
        rows = self.store.search(query.strip(), offset, limit + 1)
        return CatalogPage(items=rows[:limit], offset=offset, has_more=len(rows) > limit)

    def slots(self):
        return self.store.slots(100)[:100]

    def overview(self, actor: LibraryActor) -> LibraryOverview:
        with self.store.transaction(actor.user_id) as tx:
            self._grant(tx)
            return LibraryOverview(
                loans=[self._view(r, LoanView) for r in tx.loans() if r.owner_id == actor.user_id],
                wishes=[
                    self._view(r, WishView) for r in tx.wishes() if r.owner_id == actor.user_id
                ],
                bookings=[
                    self._view(r, BookingView) for r in tx.bookings() if r.owner_id == actor.user_id
                ],
                policy=tx.policy,
            )

    def renew(self, actor: LibraryActor, loan_id: UUID, body: RevisionInput, key: str) -> LoanView:
        with self.store.transaction(actor.user_id) as tx:
            self._grant(tx, write=True)
            operation, digest = f"renew:{loan_id}", payload_hash(body)
            replay = tx.replay(operation, key, digest)
            row = self._owned(tx.loan(replay or loan_id), actor)
            if replay:
                return self._view(row, LoanView)
            now = self._now()
            if (
                row.state != "active"
                or not row.renewable
                or row.revision != body.expected_revision
                or row.renewal_count >= tx.policy.max_renewals
                or (now >= row.due_at and not tx.policy.allow_overdue_renewal)
            ):
                raise ApiError(ErrorCode.CONFLICT)
            base = row.due_at if tx.policy.renewal_base == "due_at" else now
            due_at = base + timedelta(days=tx.policy.renewal_days)
            if due_at <= row.due_at:
                raise ApiError(ErrorCode.CONFLICT)
            return self._view(
                tx.renew(loan_id, body.expected_revision, due_at, operation, key, digest), LoanView
            )

    def request_title(self, actor: LibraryActor, body: WishInput, key: str) -> WishView:
        with self.store.transaction(actor.user_id) as tx:
            self._grant(tx, write=True)
            operation, digest = "wish:create", payload_hash(body)
            replay = tx.replay(operation, key, digest)
            row = (
                self._owned(tx.wish(replay), actor)
                if replay
                else tx.request_title(body, self._now(), operation, key, digest)
            )
            return self._view(self._owned(row, actor), WishView)

    def reserve(
        self, actor: LibraryActor, slot_id: UUID, body: RevisionInput, key: str
    ) -> BookingView:
        with self.store.transaction(actor.user_id) as tx:
            self._grant(tx, write=True)
            operation, digest = f"reserve:{slot_id}", payload_hash(body)
            replay = tx.replay(operation, key, digest)
            if replay:
                return self._view(self._owned(tx.booking(replay), actor), BookingView)
            slot, now = tx.slot(slot_id), self._now()
            if slot is None:
                raise ApiError(ErrorCode.NOT_FOUND)
            if (
                not slot.available
                or slot.starts_at <= now
                or slot.revision != body.expected_revision
            ):
                raise ApiError(ErrorCode.CONFLICT)
            active = sum(
                r.state == "reserved" and r.ends_at > now
                for r in tx.bookings()
                if r.owner_id == actor.user_id
            )
            if active >= tx.policy.max_active_bookings:
                raise ApiError(ErrorCode.CONFLICT)
            return self._view(
                tx.reserve(slot_id, body.expected_revision, now, operation, key, digest),
                BookingView,
            )

    def cancel(
        self, actor: LibraryActor, booking_id: UUID, body: RevisionInput, key: str
    ) -> BookingView:
        with self.store.transaction(actor.user_id) as tx:
            self._grant(tx, write=True)
            operation, digest = f"cancel:{booking_id}", payload_hash(body)
            replay = tx.replay(operation, key, digest)
            row = self._owned(tx.booking(replay or booking_id), actor)
            if replay:
                return self._view(row, BookingView)
            now = self._now()
            if (
                row.state != "reserved"
                or row.revision != body.expected_revision
                or row.starts_at <= now
            ):
                raise ApiError(ErrorCode.CONFLICT)
            return self._view(
                tx.cancel(booking_id, body.expected_revision, now, operation, key, digest),
                BookingView,
            )
