from collections.abc import Callable
from datetime import datetime
from threading import Lock
from uuid import UUID, uuid4

from app.core.errors import ApiError
from app.schemas.common import ErrorCode, utc_now

from .models import (
    GLOBAL_MAX,
    PER_USER_MAX,
    DemoChannelRecord,
    DemoChannelRequestCreate,
    DemoChannelRequestView,
    RequestedKind,
    RequestStatus,
)


class DemoChannelsStore:
    """In-process DEMO store. Resets on restart; never MariaDB, never a real channel.

    OFFICIAL requests stay ``PENDING_REVIEW`` permanently: there is deliberately no method that
    approves, badges, or grants roles.
    """

    def __init__(
        self,
        *,
        clock: Callable[[], datetime] = utc_now,
        id_factory: Callable[[], UUID] = uuid4,
        per_user_max: int = PER_USER_MAX,
        global_max: int = GLOBAL_MAX,
    ):
        self._lock = Lock()
        self._rows: dict[UUID, DemoChannelRecord] = {}
        self._clock, self._id_factory = clock, id_factory
        self._per_user_max, self._global_max = per_user_max, global_max

    def list_own(self, owner_id: UUID) -> list[DemoChannelRequestView]:
        with self._lock:
            rows = [row for row in self._rows.values() if row.owner_id == owner_id]
        return [row.view() for row in reversed(rows)]

    def create(self, owner_id: UUID, body: DemoChannelRequestCreate) -> DemoChannelRequestView:
        now = self._clock()
        if now.tzinfo is None:
            raise ApiError(ErrorCode.UNAVAILABLE)
        status = (
            RequestStatus.CREATED
            if body.requested_kind is RequestedKind.FREE
            else RequestStatus.PENDING_REVIEW
        )
        with self._lock:
            if len(self._rows) >= self._global_max:
                raise ApiError(ErrorCode.UNAVAILABLE)
            if sum(row.owner_id == owner_id for row in self._rows.values()) >= self._per_user_max:
                raise ApiError(ErrorCode.CONFLICT)
            row = DemoChannelRecord(
                id=self._id_factory(),
                owner_id=owner_id,
                purpose=body.purpose,
                requested_kind=body.requested_kind,
                status=status,
                revision=1,
                created_at=now,
            )
            if row.id in self._rows:
                raise ApiError(ErrorCode.CONFLICT)
            self._rows[row.id] = row
        return row.view()

    def cancel(self, owner_id: UUID, request_id: UUID, revision: int) -> UUID:
        with self._lock:
            row = self._rows.get(request_id)
            if row is None or row.owner_id != owner_id:
                raise ApiError(ErrorCode.NOT_FOUND)  # foreign rows are indistinguishable
            if row.revision != revision:
                raise ApiError(ErrorCode.CONFLICT)
            del self._rows[request_id]
        return request_id
