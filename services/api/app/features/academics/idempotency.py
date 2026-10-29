"""Idempotent create claims: (actor, method, canonical path, key) + canonical payload hash.

The claim is written in the same unit of work as the created row. A replay with the same hash
returns the current state of the original row (including a dropped/withdrawn tombstone, never a
resurrected copy) only after the caller has re-checked current permission. Same key with a
different hash is CONFLICT. Claim retention/TTL is a DB-owner decision and is not fixed here.
"""

import hashlib
import json
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from app.core.errors import ApiError
from app.schemas.common import ErrorCode

KEY_PATTERN = r"^[A-Za-z0-9-]{16,100}$"


@dataclass(frozen=True, slots=True)
class IdempotencyClaim:
    """``actor_id`` and the claim never leave the server."""

    actor_id: UUID
    method: str
    canonical_path: str
    key: str
    payload_hash: str
    resource_id: UUID

    @property
    def namespace(self) -> tuple[UUID, str, str, str]:
        return (self.actor_id, self.method, self.canonical_path, self.key)


def payload_hash(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def claim_for(
    actor_id: UUID, canonical_path: str, key: str, payload: dict[str, Any], resource_id: UUID
) -> IdempotencyClaim:
    return IdempotencyClaim(
        actor_id=actor_id,
        method="POST",
        canonical_path=canonical_path,
        key=key,
        payload_hash=payload_hash(payload),
        resource_id=resource_id,
    )


def replayed_resource(stored: IdempotencyClaim | None, attempted: IdempotencyClaim) -> UUID | None:
    """Return the original resource ID for a same-payload replay, or None for a new claim."""
    if stored is None:
        return None
    if stored.namespace != attempted.namespace:
        # A store returning another scope's claim would leak resources across actors.
        raise ApiError(ErrorCode.INTERNAL)
    if stored.payload_hash != attempted.payload_hash:
        raise ApiError(ErrorCode.CONFLICT)
    return stored.resource_id
