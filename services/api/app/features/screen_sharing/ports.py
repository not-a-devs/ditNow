"""Future authorized DB/broker boundary. No runtime implementation or second identity ledger.

Reuse current common identity, role and classroom enrollment in the SAME UOW: classroom is
the existing ClassroomTransaction, not a copied offering/grant store. Current actor identity
must be active DEMO; each grant_for check also revalidates active identity/enrollment/teacher
assignment for that same offering. Lock actor/common authorization then offering/session then
member/claim. Session mutation, members, monotonic signal sequence, bounded budgets and claims
commit atomically; every exception rolls back. One non-ended/nonexpired session per offering
is serialized/unique. Replays revalidate current sender AND recipient permission.

Claims are unique on actor+canonical operation/session path+exact case-sensitive key; compare
the payload digest and retain claims/tombstones at least until the session expires. Signal
payloads are ephemeral, not audit/event/log content: never log SDP/ICE/IP/address/track labels.
Read signal rows must be recipient- and generation-scoped before pagination. Denied members
cannot rejoin REVOKED rows or read queued payloads. Broker must recheck authorization at each
delivery and disconnect revoked transports; an HTTP flag does not revoke established P2P media.
No WS/SFU/STUN/TURN provider, account issuance, DDL, recording or audio is activated here.
"""

from collections.abc import Sequence
from contextlib import AbstractContextManager
from datetime import datetime
from typing import Protocol
from uuid import UUID

from app.features.classrooms.models import ClassroomGrant
from app.features.classrooms.ports import ClassroomTransaction
from app.features.screen_sharing.models import (
    Claim,
    Member,
    SessionRecord,
    SignalInput,
    SignalRecord,
)


class Transaction(Protocol):
    classroom: ClassroomTransaction
    actor_id: UUID
    active_demo_identity: bool

    def grant_for(self, user_id: UUID) -> ClassroomGrant | None: ...
    def current_session(self) -> SessionRecord | None: ...
    def get_session(self, session_id: UUID) -> SessionRecord | None: ...
    def insert_session(self, session: SessionRecord) -> None: ...
    def cas_session(self, session: SessionRecord, expected_revision: int) -> None: ...
    def members(self, session_id: UUID) -> Sequence[Member]: ...
    def put_member(self, session_id: UUID, member: Member) -> None: ...
    def find_claim(self, actor_id: UUID, path: str, key: str) -> Claim | None: ...
    def insert_claim(self, claim: Claim) -> None: ...

    def consume_control_budget(self, actor_id: UUID, now: datetime, maximum: int) -> None:
        """Atomic rolling15-minute actor-wide create/join/reconnect budget; rollback on failure.

        Share the budget across offerings and serialize its row/counter in this UOW. Exceeding
        maximum raises RATE_LIMITED. Do not call this for an existing valid idempotent replay.
        This is a safety throttle, not an institutional participation rule.
        """
        ...

    def signal_count(self, session_id: UUID, peer_id: UUID) -> int: ...

    def signal_bytes(self, session_id: UUID) -> int: ...
    def append_signal(
        self, session_id: UUID, sender: UUID, signal: SignalInput
    ) -> SignalRecord: ...
    def signals(
        self, session_id: UUID, recipient: UUID, generation: int, after: int, limit: int
    ) -> Sequence[SignalRecord]: ...


class Store(Protocol):
    def transaction(
        self, actor_id: UUID, offering_id: UUID
    ) -> AbstractContextManager[Transaction]: ...
