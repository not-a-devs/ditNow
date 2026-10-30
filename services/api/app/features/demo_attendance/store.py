"""Process-memory DEMO adapter for the fictional attendance sandbox (FR-ATT-003/004).

Not MariaDB persistence, not an attendance ledger and not production authorization: state is
keyed by the server-resolved actor UUID only, bounded to ``MAX_OWNERS`` and lost on restart.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from threading import Lock
from uuid import UUID

from app.schemas.common import utc_now

MAX_OWNERS = 200


class DemoAttendanceFull(Exception):
    """Raised when a new owner would exceed the bounded in-process capacity."""


@dataclass(frozen=True)
class DemoCheckIn:
    checked_in_at: datetime


class DemoAttendanceStore:
    def __init__(
        self, *, max_owners: int = MAX_OWNERS, clock: Callable[[], datetime] = utc_now
    ) -> None:
        if not 1 <= max_owners <= MAX_OWNERS:
            raise ValueError("max_owners must be within 1..200")
        self._max_owners = max_owners
        self._clock = clock
        self._lock = Lock()
        self._check_ins: dict[UUID, DemoCheckIn] = {}

    def get(self, owner: UUID) -> DemoCheckIn | None:
        with self._lock:
            return self._check_ins.get(owner)

    def check_in(self, owner: UUID) -> tuple[DemoCheckIn, bool]:
        """Records one check-in per owner. Returns ``(record, created)``; repeats replay."""
        with self._lock:
            existing = self._check_ins.get(owner)
            if existing is not None:
                return existing, False
            if len(self._check_ins) >= self._max_owners:
                raise DemoAttendanceFull
            record = DemoCheckIn(checked_in_at=self._clock())
            self._check_ins[owner] = record
            return record, True

    def owner_count(self) -> int:
        with self._lock:
            return len(self._check_ins)
