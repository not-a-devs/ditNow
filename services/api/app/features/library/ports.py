from contextlib import AbstractContextManager
from datetime import datetime
from typing import Protocol
from uuid import UUID

from app.features.library.models import (
    BookingRecord,
    CatalogTitle,
    LibraryPolicy,
    LoanRecord,
    MemberGrant,
    Slot,
    WishInput,
    WishRecord,
)


class LibraryTransaction(Protocol):
    """One adapter transaction revalidates current identity/eligibility and owns all locks.

    Reads are user-scoped and bounded. Writes must lock loans/physical item/space slots,
    enforce ownership/CAS, active-loan uniqueness and overlapping [start,end) reservations,
    per-user limits, current permissions, and server time before commit. Idempotency keys
    are actor+operation+resource namespaced with a canonical payload hash; same key/different
    hash conflicts. Replays recheck current permission and return only this actor's resource.
    Tests use a fake; no production store or security guarantee is supplied by this Protocol.
    """

    grant: MemberGrant
    policy: LibraryPolicy

    def loans(self) -> list[LoanRecord]: ...
    def wishes(self) -> list[WishRecord]: ...
    def bookings(self) -> list[BookingRecord]: ...
    def loan(self, loan_id: UUID) -> LoanRecord | None: ...
    def wish(self, wish_id: UUID) -> WishRecord | None: ...
    def booking(self, booking_id: UUID) -> BookingRecord | None: ...
    def slot(self, slot_id: UUID) -> Slot | None: ...
    def replay(self, operation: str, key: str, payload_hash: str) -> UUID | None: ...
    def renew(
        self,
        loan_id: UUID,
        revision: int,
        due_at: datetime,
        operation: str,
        key: str,
        payload_hash: str,
    ) -> LoanRecord: ...
    def request_title(
        self, body: WishInput, now: datetime, operation: str, key: str, payload_hash: str
    ) -> WishRecord: ...
    def reserve(
        self,
        slot_id: UUID,
        revision: int,
        now: datetime,
        operation: str,
        key: str,
        payload_hash: str,
    ) -> BookingRecord: ...
    def cancel(
        self,
        booking_id: UUID,
        revision: int,
        now: datetime,
        operation: str,
        key: str,
        payload_hash: str,
    ) -> BookingRecord: ...


class LibraryStore(Protocol):
    def search(self, query: str, offset: int, limit: int) -> list[CatalogTitle]: ...
    def slots(self, limit: int) -> list[Slot]: ...
    def transaction(self, user_id: UUID) -> AbstractContextManager[LibraryTransaction]: ...
