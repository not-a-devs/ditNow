import hashlib
import json
import re
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime
from threading import RLock
from uuid import UUID, uuid4

from app.core.errors import ApiError
from app.schemas.common import ErrorCode

from .models import (
    KEY_PATTERN,
    AdminChangeActor,
    ProposalCreate,
    ProposalList,
    ProposalRecord,
    ProposalState,
    ProposalSubmit,
    ProposalView,
)

# Technical memory caps only; not institutional policy. Tombstones count and are never evicted.
OWNER_CAP = 20
TOTAL_CAP = 500
OWNER_KEY_CAP = 100
TOTAL_KEY_CAP = 2_000


class AdminChangeRequestService:
    """DEMO PROCESS_MEMORY store. Restart resets everything; nothing has official effect."""

    def __init__(
        self,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        id_factory: Callable[[], str] = lambda: str(uuid4()),
    ):
        self.clock, self.id_factory = clock, id_factory
        self._lock = RLock()
        self._rows: dict[str, ProposalRecord] = {}
        # (owner, key) -> (digest, receipt). Receipts are the original response snapshot.
        self._keys: dict[tuple[UUID, str], tuple[str, ProposalView]] = {}

    @staticmethod
    def _authorize(actor: AdminChangeActor | None) -> UUID:
        if actor is None or not isinstance(actor, AdminChangeActor):
            raise ApiError(ErrorCode.UNAUTHORIZED)
        if not isinstance(actor.user_id, UUID):
            raise ApiError(ErrorCode.UNAUTHORIZED)
        if actor.can_manage is not True:
            raise ApiError(ErrorCode.FORBIDDEN)
        return actor.user_id

    @staticmethod
    def _key(key: str) -> str:
        if not isinstance(key, str) or not re.fullmatch(KEY_PATTERN, key):
            raise ApiError(ErrorCode.VALIDATION)
        return key

    @staticmethod
    def _digest(op: str, payload: dict) -> str:
        raw = json.dumps({"op": op, **payload}, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(raw.encode()).hexdigest()

    def _now(self) -> datetime:
        now = self.clock()
        if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
            raise ApiError(ErrorCode.UNAVAILABLE)
        return now.astimezone(UTC)

    @staticmethod
    def _view(row: ProposalRecord) -> ProposalView:
        return ProposalView(
            id=row.id,
            target_code=row.target_code,
            proposal_scope=row.proposal_scope,
            reason_code=row.reason_code,
            state=row.state,
            revision=row.revision,
            created_at=row.created_at,
            updated_at=row.updated_at,
            submitted_at=row.submitted_at,
            withdrawn_at=row.withdrawn_at,
        )

    def _replay(self, owner: UUID, key: str, digest: str) -> ProposalView | None:
        found = self._keys.get((owner, key))
        if found is None:
            return None
        if found[0] != digest:
            raise ApiError(ErrorCode.CONFLICT)
        return found[1].model_copy(update={"replayed": True})

    def _remember(self, owner: UUID, key: str, digest: str, view: ProposalView) -> None:
        self._keys[(owner, key)] = (digest, view)

    def _key_room(self, owner: UUID) -> None:
        owned = sum(1 for k in self._keys if k[0] == owner)
        if owned >= OWNER_KEY_CAP or len(self._keys) >= TOTAL_KEY_CAP:
            raise ApiError(ErrorCode.RATE_LIMITED)

    def _owned(self, owner: UUID, proposal_id: str) -> ProposalRecord:
        row = self._rows.get(proposal_id)
        # Unknown and foreign ids are indistinguishable.
        if row is None or row.owner_id != owner:
            raise ApiError(ErrorCode.NOT_FOUND)
        return row

    def list_own(self, actor: AdminChangeActor | None) -> ProposalList:
        with self._lock:
            owner = self._authorize(actor)
            rows = [row for row in self._rows.values() if row.owner_id == owner]
            rows.sort(key=lambda row: (row.created_at, row.id), reverse=True)
            return ProposalList(items=[self._view(row) for row in rows], owner_cap=OWNER_CAP)

    def create(
        self, actor: AdminChangeActor | None, body: ProposalCreate, key: str
    ) -> ProposalView:
        with self._lock:
            owner = self._authorize(actor)
            key = self._key(key)
            digest = self._digest("create", body.model_dump(mode="json"))
            replayed = self._replay(owner, key, digest)
            if replayed is not None:
                return replayed
            self._key_room(owner)
            if (
                sum(1 for row in self._rows.values() if row.owner_id == owner) >= OWNER_CAP
                or len(self._rows) >= TOTAL_CAP
            ):
                raise ApiError(ErrorCode.RATE_LIMITED)
            proposal_id = self.id_factory()
            if proposal_id in self._rows:
                raise ApiError(ErrorCode.UNAVAILABLE)
            now = self._now()
            row = ProposalRecord(
                id=proposal_id,
                owner_id=owner,
                target_code=body.target_code,
                proposal_scope=body.proposal_scope,
                reason_code=body.reason_code,
                state=ProposalState.DRAFT,
                revision=1,
                created_at=now,
                updated_at=now,
            )
            self._rows[proposal_id] = row
            view = self._view(row)
            self._remember(owner, key, digest, view)
            return view

    def submit(
        self, actor: AdminChangeActor | None, proposal_id: str, body: ProposalSubmit, key: str
    ) -> ProposalView:
        with self._lock:
            owner = self._authorize(actor)
            key = self._key(key)
            row = self._owned(owner, proposal_id)
            digest = self._digest(
                "submit", {"id": proposal_id, "expected_revision": body.expected_revision}
            )
            replayed = self._replay(owner, key, digest)
            if replayed is not None:
                return replayed
            self._key_room(owner)
            if row.state is not ProposalState.DRAFT or row.revision != body.expected_revision:
                raise ApiError(ErrorCode.CONFLICT)
            now = self._now()
            saved = replace(
                row,
                state=ProposalState.SUBMITTED,
                revision=row.revision + 1,
                updated_at=now,
                submitted_at=now,
            )
            self._rows[proposal_id] = saved
            view = self._view(saved)
            self._remember(owner, key, digest, view)
            return view

    def withdraw(
        self, actor: AdminChangeActor | None, proposal_id: str, revision: int
    ) -> ProposalView:
        with self._lock:
            owner = self._authorize(actor)
            row = self._owned(owner, proposal_id)
            if row.state is ProposalState.WITHDRAWN or row.revision != revision:
                raise ApiError(ErrorCode.CONFLICT)
            now = self._now()
            # Tombstone: the record stays for audit; only state/revision/timestamps change.
            saved = replace(
                row,
                state=ProposalState.WITHDRAWN,
                revision=row.revision + 1,
                updated_at=now,
                withdrawn_at=now,
            )
            self._rows[proposal_id] = saved
            return self._view(saved)
