import hashlib
import json
from collections.abc import Callable
from datetime import UTC, datetime
from uuid import UUID, uuid4

from app.core.errors import ApiError
from app.features.student_life.models import (
    CancelInput,
    ChangeInput,
    CreateInput,
    DemoBadgeView,
    GuidePage,
    LifeActor,
    LifeOverview,
    LifeRequestRecord,
    LifeRequestView,
)
from app.features.student_life.ports import LifeStore, LifeTransaction
from app.schemas.common import ApiModel, ErrorCode


def digest(body: ApiModel):
    return hashlib.sha256(
        json.dumps(body.model_dump(mode="json"), sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


class StudentLifeService:
    def __init__(self, store: LifeStore, clock: Callable[[], datetime] = lambda: datetime.now(UTC)):
        self.store, self.clock = store, clock

    def _now(self):
        now = self.clock()
        if now.tzinfo is None or now.utcoffset() is None:
            raise ApiError(ErrorCode.UNAVAILABLE)
        return now.astimezone(UTC)

    @staticmethod
    def _grant(tx: LifeTransaction):
        if not tx.grant.active:
            raise ApiError(ErrorCode.FORBIDDEN)
        if tx.policies() is None:
            raise ApiError(ErrorCode.UNAVAILABLE)

    @staticmethod
    def _owned(tx, actor, id):
        row = tx.get(id)
        if (
            row is None
            or row.owner_id != actor.user_id
            or row.program_id not in tx.grant.program_ids
        ):
            raise ApiError(ErrorCode.NOT_FOUND)
        return row

    @staticmethod
    def _view(row):
        return LifeRequestView(**row.model_dump(exclude={"owner_id"}))

    @staticmethod
    def _policy(tx, program_id, expected):
        if program_id not in tx.grant.program_ids:
            raise ApiError(ErrorCode.NOT_FOUND)
        policy = tx.policy(program_id)
        if policy is None:
            raise ApiError(ErrorCode.UNAVAILABLE)
        if policy.program_id != program_id or policy.revision != expected:
            raise ApiError(ErrorCode.CONFLICT)
        return policy

    def guides(self, offset, limit):
        rows = self.store.guides(offset, limit + 1)
        return GuidePage(items=rows[:limit], offset=offset, has_more=len(rows) > limit)

    def overview(self, actor: LifeActor):
        with self.store.transaction(actor.user_id) as tx:
            self._grant(tx)
            return LifeOverview(
                requests=[
                    self._view(row)
                    for row in tx.requests()
                    if row.owner_id == actor.user_id and row.program_id in tx.grant.program_ids
                ],
                badges=[
                    DemoBadgeView(**row.model_dump(exclude={"owner_id"}))
                    for row in tx.badges()
                    if row.owner_id == actor.user_id
                ],
                policies=[p for p in tx.policies() if p.program_id in tx.grant.program_ids],
            )

    def create(self, actor: LifeActor, body: CreateInput, key: str):
        with self.store.transaction(actor.user_id) as tx:
            self._grant(tx)
            op, hashed = "life-request:create", digest(body)
            old = tx.replay(op, key, hashed)
            if old:
                return self._view(self._owned(tx, actor, old))
            p, now = self._policy(tx, body.program_id, body.expected_policy_revision), self._now()
            if not p.opens_at <= now < p.closes_at:
                raise ApiError(ErrorCode.CONFLICT)
            if body.choice not in p.allowed_choices:
                raise ApiError(ErrorCode.VALIDATION)
            own_count = sum(
                r.owner_id == actor.user_id
                and r.program_id == p.program_id
                and r.state != "cancelled"
                for r in tx.requests()
            )
            if own_count >= p.max_per_user or tx.program_count(p.program_id) >= p.capacity:
                raise ApiError(ErrorCode.CONFLICT)
            row = LifeRequestRecord(
                id=uuid4(),
                owner_id=actor.user_id,
                program_id=p.program_id,
                kind=p.kind,
                choice=body.choice,
                state="requested",
                revision=1,
                policy_revision=p.revision,
                created_at=now,
                updated_at=now,
            )
            stored = tx.create(row, op, key, hashed)
            return self._view(self._owned(tx, actor, stored.id))

    def change(
        self, actor: LifeActor, id: UUID, body: ChangeInput | CancelInput, key: str, cancel=False
    ):
        with self.store.transaction(actor.user_id) as tx:
            self._grant(tx)
            row = self._owned(tx, actor, id)
            op, hashed = f"{'cancel' if cancel else 'update'}:{id}", digest(body)
            old = tx.replay(op, key, hashed)
            if old:
                if old != id:
                    raise ApiError(ErrorCode.INTERNAL)
                return self._view(self._owned(tx, actor, old))
            p, now = self._policy(tx, row.program_id, body.expected_policy_revision), self._now()
            if p.kind != row.kind or row.revision != body.expected_revision:
                raise ApiError(ErrorCode.CONFLICT)
            changes = {
                "revision": row.revision + 1,
                "policy_revision": p.revision,
                "updated_at": now,
            }
            if cancel:
                if (
                    row.state not in {"requested", "processing", "participating"}
                    or p.cancel_until is None
                    or now >= p.cancel_until
                ):
                    raise ApiError(ErrorCode.CONFLICT)
                changes["state"] = "cancelled"
            else:
                if (
                    not isinstance(body, ChangeInput)
                    or row.state != "requested"
                    or not p.opens_at <= now < p.closes_at
                ):
                    raise ApiError(ErrorCode.CONFLICT)
                if body.choice not in p.allowed_choices:
                    raise ApiError(ErrorCode.VALIDATION)
                changes["choice"] = body.choice
            stored = tx.replace(
                row.model_copy(update=changes), body.expected_revision, op, key, hashed
            )
            return self._view(self._owned(tx, actor, stored.id))
