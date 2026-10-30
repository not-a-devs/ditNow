"""Process-memory DEMO store: resets on restart, never MariaDB, never production authorization.

Cards are the same fixed fictional rows for everyone. Each owner gets three fixed notifications
whose IDs are random UUIDs allocated on first access, so an ID reveals nothing about its owner.
"""

from collections.abc import Callable
from dataclasses import dataclass
from threading import Lock
from uuid import UUID, uuid4

from app.core.errors import ApiError
from app.features.demo_action_center.models import (
    DemoCard,
    DemoCardKind,
    DemoNotification,
    DemoReadResult,
    DemoSummary,
)
from app.schemas.common import ErrorCode

MAX_OWNERS = 200

# Stable in-app paths only; never external URLs or client-supplied links.
LINKS: dict[DemoCardKind, str] = {
    DemoCardKind.CLASS: "/app/classrooms",
    DemoCardKind.TASK: "/app/classrooms",
    DemoCardKind.NOTICE: "/app/department",
}

CARDS: tuple[DemoCard, ...] = (
    DemoCard(
        id="demo-class-1",
        kind=DemoCardKind.CLASS,
        title="[DEMO] 가상 자료구조 수업",
        detail="가상 시연용 수업 카드입니다. 실제 시간표가 아닙니다.",
        link=LINKS[DemoCardKind.CLASS],
    ),
    DemoCard(
        id="demo-task-1",
        kind=DemoCardKind.TASK,
        title="[DEMO] 가상 과제 제출 연습",
        detail="가상 시연용 과제 카드입니다. 실제 과제·마감이 아닙니다.",
        link=LINKS[DemoCardKind.TASK],
    ),
    DemoCard(
        id="demo-notice-1",
        kind=DemoCardKind.NOTICE,
        title="[DEMO] 가상 학과 안내",
        detail="가상 시연용 안내 카드입니다. 공식 공지가 아닙니다.",
        link=LINKS[DemoCardKind.NOTICE],
    ),
)

# (template key, card id, title) — three per owner, in fixed order.
NOTIFICATION_TEMPLATES: tuple[tuple[str, str, str], ...] = (
    ("class", "demo-class-1", "[DEMO] 가상 수업 카드가 준비되었습니다"),
    ("task", "demo-task-1", "[DEMO] 가상 과제 카드를 확인해 보세요"),
    ("notice", "demo-notice-1", "[DEMO] 가상 안내 카드가 추가되었습니다"),
)
_CARD_LINKS = {card.id: card.link for card in CARDS}


@dataclass
class _Row:
    id: UUID
    card_id: str
    title: str
    read: bool = False
    revision: int = 1

    def view(self) -> DemoNotification:
        return DemoNotification(
            id=self.id,
            card_id=self.card_id,
            title=self.title,
            link=_CARD_LINKS[self.card_id],
            read=self.read,
            revision=self.revision,
        )


class DemoActionCenterStore:
    """Thread-safe in-process exercise state; the root installs one on ``app.state``."""

    def __init__(self, *, max_owners: int = MAX_OWNERS, id_factory: Callable[[], UUID] = uuid4):
        self._lock = Lock()
        self._max_owners = max_owners
        self._id_factory = id_factory
        self._owners: dict[UUID, list[_Row]] = {}
        self._index: dict[UUID, tuple[UUID, _Row]] = {}

    def reset(self) -> None:
        with self._lock:
            self._owners.clear()
            self._index.clear()

    def _rows(self, owner: UUID) -> list[_Row]:
        rows = self._owners.get(owner)
        if rows is not None:
            return rows
        if len(self._owners) >= self._max_owners:
            raise ApiError(ErrorCode.UNAVAILABLE)
        rows = []
        for _, card_id, title in NOTIFICATION_TEMPLATES:
            notification_id = self._id_factory()
            # A colliding or owner-equal ID would merge or leak rows; fail closed instead.
            if notification_id in self._index or notification_id == owner:
                raise ApiError(ErrorCode.INTERNAL)
            rows.append(_Row(notification_id, card_id, title))
        self._owners[owner] = rows
        for row in rows:
            self._index[row.id] = (owner, row)
        return rows

    @staticmethod
    def _unread(rows: list[_Row]) -> int:
        return sum(not row.read for row in rows)

    def summary(self, owner: UUID) -> DemoSummary:
        with self._lock:
            rows = self._rows(owner)
            return DemoSummary(
                cards=[card.model_copy() for card in CARDS],
                notifications=[row.view() for row in rows],
                unread_count=self._unread(rows),
            )

    def mark_read(self, owner: UUID, notification_id: UUID, revision: int) -> DemoReadResult:
        with self._lock:
            found = self._index.get(notification_id)
            # Unknown and other-owner IDs are indistinguishable.
            if found is None or found[0] != owner:
                raise ApiError(ErrorCode.NOT_FOUND)
            row = found[1]
            rows = self._owners[owner]
            if row.read:
                return DemoReadResult(
                    notification=row.view(), already_read=True, unread_count=self._unread(rows)
                )
            if revision != row.revision:
                raise ApiError(ErrorCode.CONFLICT)
            row.read = True
            row.revision += 1
            return DemoReadResult(
                notification=row.view(), already_read=False, unread_count=self._unread(rows)
            )
