import hashlib
import json
from collections.abc import Callable
from datetime import UTC, datetime
from uuid import UUID, uuid4

from app.core.errors import ApiError
from app.features.admissions.models import (
    ApplicantActor,
    ApplicantOverview,
    ApplicationRecord,
    ApplicationView,
    DemoAdmissionPolicy,
    DraftCreate,
    DraftUpdate,
    GuidePage,
    TransitionInput,
)
from app.features.admissions.ports import AdmissionsStore, AdmissionTransaction
from app.schemas.common import ApiModel, ErrorCode


def digest(body: ApiModel) -> str:
    raw = json.dumps(body.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode()).hexdigest()


class AdmissionsService:
    def __init__(
        self, store: AdmissionsStore, clock: Callable[[], datetime] = lambda: datetime.now(UTC)
    ):
        self.store, self.clock = store, clock

    def _now(self):
        now = self.clock()
        if now.tzinfo is None or now.utcoffset() is None:
            raise ApiError(ErrorCode.UNAVAILABLE)
        return now.astimezone(UTC)

    @staticmethod
    def _grant(tx: AdmissionTransaction):
        if not tx.grant.active or not tx.grant.applicant:
            raise ApiError(ErrorCode.FORBIDDEN)

    @staticmethod
    def _owned(tx: AdmissionTransaction, actor: ApplicantActor, id: UUID):
        row = tx.get(id)
        if row is None or row.owner_id != actor.user_id or row.cycle_id not in tx.grant.cycle_ids:
            raise ApiError(ErrorCode.NOT_FOUND)
        return row

    @staticmethod
    def _view(row: ApplicationRecord):
        return ApplicationView(**row.model_dump(exclude={"owner_id"}))

    @staticmethod
    def _policy(tx: AdmissionTransaction, cycle_id: UUID, expected: int):
        if cycle_id not in tx.grant.cycle_ids:
            raise ApiError(ErrorCode.NOT_FOUND)
        policy = tx.policy(cycle_id)
        if policy is None:
            raise ApiError(ErrorCode.UNAVAILABLE)
        if policy.cycle_id != cycle_id or policy.revision != expected:
            raise ApiError(ErrorCode.CONFLICT)
        return policy

    @staticmethod
    def _open(policy: DemoAdmissionPolicy, now: datetime):
        if not policy.opens_at <= now < policy.closes_at:
            raise ApiError(ErrorCode.CONFLICT)

    def guides(self, offset: int, limit: int):
        rows = self.store.guides(offset, limit + 1)
        return GuidePage(items=rows[:limit], offset=offset, has_more=len(rows) > limit)

    def overview(self, actor: ApplicantActor):
        with self.store.transaction(actor.user_id) as tx:
            self._grant(tx)
            return ApplicantOverview(
                applications=[
                    self._view(r)
                    for r in tx.applications()
                    if r.owner_id == actor.user_id and r.cycle_id in tx.grant.cycle_ids
                ],
                policies=[p for p in tx.policies() if p.cycle_id in tx.grant.cycle_ids],
            )

    def create(self, actor: ApplicantActor, body: DraftCreate, key: str):
        with self.store.transaction(actor.user_id) as tx:
            self._grant(tx)
            operation, hashed = "application:create", digest(body)
            old = tx.replay(operation, key, hashed)
            if old:
                return self._view(self._owned(tx, actor, old))
            policy = self._policy(tx, body.cycle_id, body.expected_policy_revision)
            now = self._now()
            self._open(policy, now)
            if body.track_id not in {t.id for t in policy.tracks}:
                raise ApiError(ErrorCode.VALIDATION)
            count = sum(
                r.owner_id == actor.user_id and r.cycle_id == body.cycle_id
                for r in tx.applications()
            )
            if count >= policy.max_applications:
                raise ApiError(ErrorCode.CONFLICT)
            row = ApplicationRecord(
                id=uuid4(),
                cycle_id=body.cycle_id,
                owner_id=actor.user_id,
                demo_alias=body.demo_alias,
                track_id=body.track_id,
                motivation=body.motivation,
                state="draft",
                revision=1,
                policy_revision=policy.revision,
                created_at=now,
                updated_at=now,
            )
            stored = tx.create(row, operation, key, hashed)
            return self._view(self._owned(tx, actor, stored.id))

    def change(
        self,
        actor: ApplicantActor,
        id: UUID,
        body: DraftUpdate | TransitionInput,
        key: str,
        action: str,
    ):
        if action not in {"update", "submit", "withdraw"}:
            raise ApiError(ErrorCode.UNAVAILABLE)
        with self.store.transaction(actor.user_id) as tx:
            self._grant(tx)
            row = self._owned(tx, actor, id)
            operation, hashed = f"{action}:{id}", digest(body)
            old = tx.replay(operation, key, hashed)
            if old:
                if old != id:
                    raise ApiError(ErrorCode.INTERNAL)
                return self._view(self._owned(tx, actor, old))
            policy = self._policy(tx, row.cycle_id, body.expected_policy_revision)
            if row.revision != body.expected_revision:
                raise ApiError(ErrorCode.CONFLICT)
            now, updates = self._now(), {}
            if action == "update" and isinstance(body, DraftUpdate):
                self._open(policy, now)
                if row.state != "draft":
                    raise ApiError(ErrorCode.CONFLICT)
                if body.track_id not in {t.id for t in policy.tracks}:
                    raise ApiError(ErrorCode.VALIDATION)
                updates = body.model_dump(exclude={"expected_revision", "expected_policy_revision"})
                updates["policy_revision"] = policy.revision
            elif action == "submit":
                self._open(policy, now)
                if row.state != "draft" or row.policy_revision != policy.revision:
                    raise ApiError(ErrorCode.CONFLICT)
                if row.track_id not in {t.id for t in policy.tracks}:
                    raise ApiError(ErrorCode.CONFLICT)
                updates["state"] = "submitted"
            elif action == "withdraw":
                if (
                    row.state not in {"submitted", "received"}
                    or policy.withdrawal_closes_at is None
                    or now >= policy.withdrawal_closes_at
                ):
                    raise ApiError(ErrorCode.CONFLICT)
                updates["state"] = "withdrawal_requested"
            else:
                raise ApiError(ErrorCode.VALIDATION)
            updated = row.model_copy(
                update={**updates, "revision": row.revision + 1, "updated_at": now}
            )
            stored = tx.replace(updated, body.expected_revision, operation, key, hashed)
            return self._view(self._owned(tx, actor, stored.id))
