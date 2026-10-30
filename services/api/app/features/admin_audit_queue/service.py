from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass, replace
from threading import RLock
from uuid import NAMESPACE_URL, UUID, uuid5

from app.core.errors import ApiError
from app.features.admin_audit_queue.models import (
    AuditActor,
    AuditCategory,
    AuditItemView,
    AuditPatchInput,
    AuditQueuePage,
    AuditStatus,
    Classification,
    NoteCode,
    Resolution,
)
from app.schemas.common import ErrorCode

# DEMO only. Process memory; every restart resets the queue. No official moderation effect.
_NAMESPACE = uuid5(NAMESPACE_URL, "ditnow:demo:admin-audit-queue")
_FIXTURE: tuple[AuditCategory, ...] = (
    AuditCategory.NOTICE,
    AuditCategory.POST,
    AuditCategory.REPORT,
    AuditCategory.POST,
    AuditCategory.REPORT,
    AuditCategory.NOTICE,
)
MAX_OWNERS = 64
MAX_KEYS_PER_OWNER = 32


@dataclass(frozen=True)
class _Item:
    id: UUID
    category: AuditCategory
    demo_label: str
    status: AuditStatus = AuditStatus.PENDING
    classification: Classification | None = None
    resolution: Resolution | None = None
    note_code: NoteCode | None = None
    revision: int = 1

    def view(self) -> AuditItemView:
        return AuditItemView(
            id=self.id,
            category=self.category,
            demo_label=self.demo_label,
            status=self.status,
            classification=self.classification,
            resolution=self.resolution,
            note_code=self.note_code,
            revision=self.revision,
        )


def _seed(owner: UUID) -> dict[UUID, _Item]:
    items = {}
    for index, category in enumerate(_FIXTURE, start=1):
        item_id = uuid5(_NAMESPACE, f"{owner}:{index}")
        items[item_id] = _Item(id=item_id, category=category, demo_label=f"DEMO_ITEM_{index:02d}")
    return items


class AdminAuditQueueService:
    """Bounded in-memory DEMO queue. `can_review` is the trusted server grant port and is
    re-evaluated on every operation; this service never provisions roles or reads real content."""

    def __init__(
        self,
        can_review: Callable[[UUID], bool],
        *,
        max_owners: int = MAX_OWNERS,
        max_keys_per_owner: int = MAX_KEYS_PER_OWNER,
    ):
        self._can_review = can_review
        self._max_owners = max_owners
        self._max_keys = max_keys_per_owner
        self._lock = RLock()
        self._owners: dict[UUID, dict[UUID, _Item]] = {}
        self._keys: dict[UUID, OrderedDict[str, tuple[AuditPatchInput, UUID, AuditItemView]]] = {}

    def _authorize(self, actor: AuditActor | None) -> UUID:
        if actor is None:
            raise ApiError(ErrorCode.UNAUTHORIZED)
        try:
            allowed = self._can_review(actor.user_id)
        except Exception:
            raise ApiError(ErrorCode.UNAVAILABLE) from None
        if allowed is not True:
            raise ApiError(ErrorCode.FORBIDDEN)
        return actor.user_id

    def _queue(self, owner: UUID) -> dict[UUID, _Item]:
        queue = self._owners.get(owner)
        if queue is None:
            if len(self._owners) >= self._max_owners:
                raise ApiError(ErrorCode.UNAVAILABLE)
            queue = self._owners[owner] = _seed(owner)
            self._keys[owner] = OrderedDict()
        return queue

    def list_items(
        self,
        actor: AuditActor | None,
        status: AuditStatus | None = None,
        category: AuditCategory | None = None,
    ) -> AuditQueuePage:
        # Authorization runs under the same lock as the read/write/replay it guards.
        with self._lock:
            owner = self._authorize(actor)
            rows = [
                item.view()
                for item in self._queue(owner).values()
                if (status is None or item.status is status)
                and (category is None or item.category is category)
            ]
        return AuditQueuePage(items=rows)

    def get(self, actor: AuditActor | None, item_id: UUID) -> AuditItemView:
        with self._lock:
            owner = self._authorize(actor)
            item = self._queue(owner).get(item_id)
            if item is None:
                raise ApiError(ErrorCode.NOT_FOUND)
            return item.view()

    def patch(
        self,
        actor: AuditActor | None,
        item_id: UUID,
        body: AuditPatchInput,
        idempotency_key: str | None = None,
    ) -> AuditItemView:
        with self._lock:
            owner = self._authorize(actor)
            queue = self._queue(owner)
            keys = self._keys[owner]
            if idempotency_key is not None and idempotency_key in keys:
                saved_body, saved_id, receipt = keys[idempotency_key]
                if saved_body != body or saved_id != item_id:
                    raise ApiError(ErrorCode.CONFLICT)
                return receipt
            item = queue.get(item_id)
            if item is None:
                raise ApiError(ErrorCode.NOT_FOUND)
            if item.revision != body.revision:
                raise ApiError(ErrorCode.CONFLICT)
            if item.status is AuditStatus.PENDING and body.classification is not None:
                updated = replace(
                    item,
                    status=AuditStatus.CLASSIFIED,
                    classification=body.classification,
                    note_code=body.note_code,
                    revision=item.revision + 1,
                )
            elif item.status is AuditStatus.CLASSIFIED and body.resolution is not None:
                updated = replace(
                    item,
                    status=AuditStatus.RESOLVED,
                    resolution=body.resolution,
                    note_code=body.note_code,
                    revision=item.revision + 1,
                )
            else:
                # RESOLVED is immutable; out-of-order steps are state conflicts.
                raise ApiError(ErrorCode.CONFLICT)
            queue[item_id] = updated
            receipt = updated.view()
            if idempotency_key is not None:
                keys[idempotency_key] = (body, item_id, receipt)
                while len(keys) > self._max_keys:
                    keys.popitem(last=False)
            return receipt
