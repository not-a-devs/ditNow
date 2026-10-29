"""Server-only snapshots. No password, session copy, or public identity projection."""

from collections.abc import AsyncIterator, Sequence
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal, Protocol
from uuid import UUID

from pydantic import ConfigDict, SecretStr

from app.schemas.common import ApiModel


class BridgePrincipal(ApiModel):
    """Internal dependency result, compatible with the proposed P0 principal seam.

    This is NOT a student-facing/anonymous response and does not grant a resource action.
    """

    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)
    user_id: UUID
    active: Literal[True] = True


@dataclass(frozen=True)
class ApprovedMapping:
    issuer: str = field(repr=False)
    subject: str = field(repr=False)
    user_id: UUID
    approved_by: UUID
    approved_at: datetime
    legacy_source_kind: str
    active: bool = True
    revoked_at: datetime | None = None


@dataclass(frozen=True)
class CurrentIdentity:
    user_id: UUID
    issuer: str = field(repr=False)
    subject: str = field(repr=False)
    status: str
    source_kind: str


@dataclass(frozen=True)
class CurrentProfile:
    user_id: UUID
    source_kind: str


@dataclass(frozen=True)
class CurrentMembership:
    user_id: UUID
    department_id: UUID
    academic_year: int
    status: str
    valid_from: datetime
    valid_to: datetime | None = None


@dataclass(frozen=True)
class CurrentRole:
    user_id: UUID
    role: str
    scope_type: str
    scope_id: UUID | None
    status: str
    valid_from: datetime
    valid_to: datetime | None = None


class LegacyTokenVerifier(Protocol):
    async def verify(self, token: SecretStr) -> str | None:
        """Return the canonical existing student PK from current session authority only."""
        ...


class IdentityReadTransaction(Protocol):
    """Current common ledger, never an alias/password/session store.

    Implementations must use a fresh server-owned UOW and current locking reads (not token
    claims/cache). Lock identity/profile/membership/roles in a consistent order, and serialize
    approval revocation/subject reassignment against these reads. Mapping queries must return
    ALL candidates, including duplicates/collation aliases, not LIMIT 1. No provisioning.
    Read errors propagate to the bridge's sanitized 503; they must not become empty approvals.
    """

    async def mappings_for_subject(
        self, issuer: str, subject: str
    ) -> Sequence[ApprovedMapping]: ...
    async def mappings_for_user(self, user_id: UUID) -> Sequence[ApprovedMapping]: ...
    async def identity(self, user_id: UUID) -> CurrentIdentity | None: ...
    async def profile(self, user_id: UUID) -> CurrentProfile | None: ...
    async def memberships(self, user_id: UUID) -> Sequence[CurrentMembership]: ...
    async def roles(self, user_id: UUID) -> Sequence[CurrentRole]: ...


class IdentityLedger(Protocol):
    def transaction(self) -> AbstractAsyncContextManager[IdentityReadTransaction]: ...


# Public for implementers' asynccontextmanager annotations; no runtime implementation is bundled.
IdentityTransactionIterator = AsyncIterator[IdentityReadTransaction]
