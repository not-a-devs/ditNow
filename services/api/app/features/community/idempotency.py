"""Idempotent create requests for the community feature.

Mirrors the reviewed ``IdempotencyScope`` contract (PR #13, not yet on main): a key is scoped by
``(actor, method, canonical path, key)``; the request body digest is stored with the claim so a
reused key with a different body is a 409, not a new resource. Revision (CAS) checks on
PATCH/DELETE/close are independent of this module and are never bypassed by a key.

Storage of claims is atomic with the created resource (see ``repository.py``). Retention/TTL of
claims is a DB-owner decision and is not fixed here.
"""

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any, Literal

from app.core.errors import ApiError
from app.schemas.common import ErrorCode

IDEMPOTENCY_HEADER = "Idempotency-Key"
KEY_PATTERN = r"^[!-~]{1,128}$"
_KEY_RE = re.compile(KEY_PATTERN)

Method = Literal["POST"]


@dataclass(frozen=True, slots=True)
class IdempotencyClaim:
    """A stored ``key -> resource`` binding. ``actor_id`` never leaves the server."""

    actor_id: str
    method: Method
    canonical_path: str
    key: str
    body_digest: str
    resource_id: str

    @property
    def namespace(self) -> tuple[str, str, str, str]:
        return (self.actor_id, self.method, self.canonical_path, self.key)


def body_digest(payload: dict[str, Any]) -> str:
    """SHA-256 of the validated, normalized body (sorted keys) so semantic retries match."""
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def new_claim(
    *,
    actor_id: str,
    canonical_path: str,
    key: str,
    payload: dict[str, Any],
    resource_id: str,
) -> IdempotencyClaim:
    if not _KEY_RE.fullmatch(key):
        raise ApiError(ErrorCode.VALIDATION)
    return IdempotencyClaim(
        actor_id=actor_id,
        method="POST",
        canonical_path=canonical_path,
        key=key,
        body_digest=body_digest(payload),
        resource_id=resource_id,
    )


def is_replay(stored: IdempotencyClaim, attempted: IdempotencyClaim) -> bool:
    """Compare the claim the repository kept with the one this request tried to store.

    Same body -> replay of ``stored.resource_id``; different body under the same key -> 409.
    """
    if stored.namespace != attempted.namespace:
        # A repository returning another scope's claim would leak resources across actors.
        raise ApiError(ErrorCode.INTERNAL)
    if stored.body_digest != attempted.body_digest:
        raise ApiError(ErrorCode.CONFLICT)
    return stored.resource_id != attempted.resource_id
