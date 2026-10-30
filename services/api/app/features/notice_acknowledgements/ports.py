"""Inactive contracts only; no auth/session issuance, role provisioning or DB binding.

Actor: supplied only by the approved common identity bridge (server-verified UUID). Clients
never send owner, role or audience; request bodies forbid extra fields.

NoticeAccessPort: the existing campus notice ledger is authoritative. The service calls
``resolve`` on EVERY operation while holding the store lock, so owner/audience changes and
revocations apply immediately. A DB adapter MUST read the current notice owner and current
audience in the same transaction/UOW that writes acknowledgement rows and idempotency claims
(lock order: notice row -> ack request -> ack/claim) and roll everything back on failure.
The port must not return notice text; this module never stores or echoes notice content.
The port decides eligibility; this module does not infer audience policy.
"""

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID


@dataclass(frozen=True)
class Actor:
    user_id: UUID


@dataclass(frozen=True)
class NoticeAccess:
    owner_id: UUID
    audience: frozenset[UUID]
    eligible_total: int


class NoticeAccessPort(Protocol):
    def resolve(self, notice_id: UUID) -> NoticeAccess | None: ...
