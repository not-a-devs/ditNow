"""DEMO acknowledgement service backed by an explicitly injected, bounded process-memory store.

Nothing persists: a process restart resets every request, acknowledgement and claim
(official_effect=false). One RLock covers port resolution, CAS checks, idempotency claims and
writes so each operation is a single unit of work.
"""

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from threading import RLock
from uuid import UUID

from app.core.errors import ApiError
from app.features.notice_acknowledgements.models import (
    AckInput,
    AckReceipt,
    AckRequestInput,
    AckRequestView,
    AckSummary,
    OwnState,
)
from app.features.notice_acknowledgements.ports import Actor, NoticeAccess, NoticeAccessPort
from app.schemas.common import ErrorCode

KEY_PATTERN = r"^[A-Za-z0-9_-]{16,128}$"
MAX_REQUESTS = 1_000
MAX_ACKS = 50_000
MAX_CLAIMS = 50_000
MAX_AUDIENCE = 10_000


@dataclass
class DemoAckStore:
    requests: dict[UUID, int] = field(default_factory=dict)
    acks: dict[UUID, dict[UUID, datetime]] = field(default_factory=dict)
    ack_total: int = 0
    claims: dict[tuple[UUID, str, UUID, str], tuple[str, object]] = field(default_factory=dict)
    lock: RLock = field(default_factory=RLock)


def _digest(payload: dict) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode()).hexdigest()


class NoticeAcknowledgementService:
    def __init__(
        self,
        port: NoticeAccessPort,
        store: DemoAckStore,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ):
        self._port = port
        self._store = store
        self._clock = clock

    def _access(self, actor: Actor, notice_id: UUID) -> tuple[NoticeAccess, bool, bool]:
        access = self._port.resolve(notice_id)
        if access is None:
            raise ApiError(ErrorCode.NOT_FOUND)
        if len(access.audience) > MAX_AUDIENCE or access.eligible_total != len(access.audience):
            raise ApiError(ErrorCode.UNAVAILABLE)
        is_owner = access.owner_id == actor.user_id
        member = actor.user_id in access.audience
        if not (is_owner or member):
            raise ApiError(ErrorCode.NOT_FOUND)
        return access, is_owner, member

    def _claim(self, actor: Actor, op: str, notice_id: UUID, key: str, digest: str):
        claim = self._store.claims.get((actor.user_id, op, notice_id, key))
        if claim is None:
            if len(self._store.claims) >= MAX_CLAIMS:
                raise ApiError(ErrorCode.RATE_LIMITED)
            return None
        if claim[0] != digest:
            raise ApiError(ErrorCode.CONFLICT)
        return claim[1]

    def request(self, actor: Actor, body: AckRequestInput, key: str) -> AckRequestView:
        store = self._store
        with store.lock:
            _, is_owner, _ = self._access(actor, body.notice_id)
            if not is_owner:
                raise ApiError(ErrorCode.FORBIDDEN)
            digest = _digest(body.model_dump(mode="json"))
            replay = self._claim(actor, "request", body.notice_id, key, digest)
            if replay is not None:
                return replay
            current = store.requests.get(body.notice_id)
            if body.revision is not None and body.revision != (current or 0):
                raise ApiError(ErrorCode.CONFLICT)
            if current is None:
                if len(store.requests) >= MAX_REQUESTS:
                    raise ApiError(ErrorCode.RATE_LIMITED)
                current = 1
            view = AckRequestView(notice_id=body.notice_id, request_revision=current)
            store.requests[body.notice_id] = current
            store.claims[(actor.user_id, "request", body.notice_id, key)] = (digest, view)
            return view

    def state(self, actor: Actor, notice_id: UUID) -> OwnState:
        with self._store.lock:
            _, is_owner, member = self._access(actor, notice_id)
            revision = self._store.requests.get(notice_id)
            at = self._store.acks.get(notice_id, {}).get(actor.user_id) if member else None
            return OwnState(
                notice_id=notice_id,
                requested=revision is not None,
                request_revision=revision,
                can_request=is_owner and revision is None,
                can_acknowledge=member and revision is not None and at is None,
                acknowledged=at is not None,
                acknowledged_at=at,
                can_view_summary=is_owner and revision is not None,
            )

    def acknowledge(self, actor: Actor, notice_id: UUID, body: AckInput, key: str) -> AckReceipt:
        store = self._store
        with store.lock:
            _, _, member = self._access(actor, notice_id)
            if not member:
                raise ApiError(ErrorCode.FORBIDDEN)
            revision = store.requests.get(notice_id)
            if revision is None:
                raise ApiError(ErrorCode.NOT_FOUND)
            digest = _digest(body.model_dump(mode="json"))
            replay = self._claim(actor, "ack", notice_id, key, digest)
            if replay is not None:
                return replay
            if body.request_revision != revision:
                raise ApiError(ErrorCode.CONFLICT)
            acks = store.acks.setdefault(notice_id, {})
            at = acks.get(actor.user_id)
            if at is None:
                if store.ack_total >= MAX_ACKS:
                    raise ApiError(ErrorCode.RATE_LIMITED)
                at = self._clock()
                acks[actor.user_id] = at
                store.ack_total += 1
            receipt = AckReceipt(notice_id=notice_id, request_revision=revision, acknowledged_at=at)
            store.claims[(actor.user_id, "ack", notice_id, key)] = (digest, receipt)
            return receipt

    def summary(self, actor: Actor, notice_id: UUID) -> AckSummary:
        with self._store.lock:
            access, is_owner, _ = self._access(actor, notice_id)
            if not is_owner:
                raise ApiError(ErrorCode.FORBIDDEN)
            revision = self._store.requests.get(notice_id)
            if revision is None:
                raise ApiError(ErrorCode.NOT_FOUND)
            acked = self._store.acks.get(notice_id, {}).keys() & access.audience
            return AckSummary(
                notice_id=notice_id,
                request_revision=revision,
                eligible_total=access.eligible_total,
                acknowledged_count=len(acked),
            )
