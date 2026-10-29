import hashlib
import json
import re
from collections.abc import Callable
from datetime import UTC, datetime

from app.core.errors import ApiError
from app.schemas.common import ErrorCode

from .models import ActivityProfileRecord, ProfileActor, ProfileUpdate, ProfileView
from .ports import ProfileConflict, ProfileStore


class ProfileService:
    def __init__(
        self, store: ProfileStore, clock: Callable[[], datetime] = lambda: datetime.now(UTC)
    ):
        self.store, self.clock = store, clock

    @staticmethod
    def _current(tx, actor: ProfileActor) -> ActivityProfileRecord:
        if tx.access.user_id != actor.user_id or not tx.access.active:
            raise ApiError(ErrorCode.UNAUTHORIZED)
        if not tx.access.current_student or tx.access.record_source != "DEMO":
            raise ApiError(ErrorCode.FORBIDDEN)
        if tx.policy is None:
            raise ApiError(ErrorCode.UNAVAILABLE)
        row = tx.self_profile()
        if row is None or row.user_id != actor.user_id:
            raise ApiError(ErrorCode.NOT_FOUND)
        return row

    @staticmethod
    def _view(tx, row, *, replayed=False):
        return ProfileView(
            **row.model_dump(exclude={"user_id"}), policy=tx.policy, replayed=replayed
        )

    def get(self, actor: ProfileActor):
        with self.store.transaction(actor.user_id) as tx:
            return self._view(tx, self._current(tx, actor))

    def update(self, actor: ProfileActor, body: ProfileUpdate, key: str):
        if not isinstance(key, str) or not re.fullmatch(r"[A-Za-z0-9-]{16,100}", key):
            raise ApiError(ErrorCode.VALIDATION)
        digest = hashlib.sha256(
            json.dumps(body.model_dump(mode="json"), sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        try:
            with self.store.transaction(actor.user_id) as tx:
                row = self._current(tx, actor)
                if body.expected_policy_revision != tx.policy.revision:
                    raise ApiError(ErrorCode.CONFLICT)
                edits = body.model_dump(exclude={"expected_revision", "expected_policy_revision"})
                if any(
                    getattr(row, field) != value and field not in tx.policy.editable_fields
                    for field, value in edits.items()
                ):
                    raise ApiError(ErrorCode.FORBIDDEN)
                if tx.replay(key, digest):
                    return self._view(tx, row, replayed=True)
                if row.revision != body.expected_revision:
                    raise ApiError(ErrorCode.CONFLICT)
                now = self.clock()
                if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
                    raise ApiError(ErrorCode.UNAVAILABLE)
                changed = row.model_copy(
                    update={
                        **edits,
                        "revision": row.revision + 1,
                        "updated_at": now.astimezone(UTC),
                    }
                )
                saved = tx.save(changed, row.revision, key, digest)
                if saved != changed:
                    raise ApiError(ErrorCode.UNAVAILABLE)
                return self._view(tx, saved)
        except ProfileConflict:
            raise ApiError(ErrorCode.CONFLICT) from None
