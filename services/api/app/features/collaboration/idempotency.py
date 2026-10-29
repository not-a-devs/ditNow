"""Idempotent create requests for the collaboration feature.

A key is scoped by ``(actor, method, canonical path, key)``; the canonical path contains the
concrete parent IDs (e.g. ``/api/v1/anonymous-posts/{post_id}/comments``), so the same key under
another parent is a different request. The validated, normalized body is hashed and stored with
the scope. Same scope + same hash -> replay; same scope + different hash -> 409.

The record is claimed inside the same UOW transaction that writes the resource (see
``ports.py``). Records are never deleted when the resource is deleted: they stay as tombstones,
so a replay after deletion answers 404 instead of recreating the resource. Revision (CAS) checks
on update/delete never consult this module. Retention/TTL is a DB-owner decision.
"""

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any, Literal

from app.core.errors import ApiError
from app.schemas.common import ErrorCode

IDEMPOTENCY_HEADER = "Idempotency-Key"
KEY_PATTERN = r"^[!-~]{8,128}$"
_KEY_RE = re.compile(KEY_PATTERN)

API_PREFIX = "/api/v1"


@dataclass(frozen=True, slots=True)
class IdempotencyScope:
    actor_id: str
    method: Literal["POST"]
    canonical_path: str
    key: str


@dataclass(frozen=True, slots=True)
class IdempotencyRecord:
    """Server-internal binding of a scope to the resource it created. Never returned."""

    scope: IdempotencyScope
    payload_hash: str
    resource_type: str
    resource_id: str


def payload_hash(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def new_record(
    *,
    actor_id: str,
    path: str,
    key: str,
    payload: dict[str, Any],
    resource_type: str,
    resource_id: str,
) -> IdempotencyRecord:
    if not _KEY_RE.fullmatch(key):
        raise ApiError(ErrorCode.VALIDATION)
    return IdempotencyRecord(
        scope=IdempotencyScope(
            actor_id=actor_id, method="POST", canonical_path=API_PREFIX + path, key=key
        ),
        payload_hash=payload_hash(payload),
        resource_type=resource_type,
        resource_id=resource_id,
    )


def replayed_resource(stored: IdempotencyRecord | None, attempted: IdempotencyRecord) -> str | None:
    """``stored`` is what ``claim`` returned: ``None`` for a fresh claim, else the kept record.

    Returns the previously created resource ID for a replay, ``None`` for a fresh claim.
    """
    if stored is None:
        return None
    if stored.scope != attempted.scope or stored.resource_type != attempted.resource_type:
        # An adapter returning another scope's record would leak resources across actors.
        raise ApiError(ErrorCode.INTERNAL)
    if stored.payload_hash != attempted.payload_hash:
        raise ApiError(ErrorCode.CONFLICT)
    return stored.resource_id
