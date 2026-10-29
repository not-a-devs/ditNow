from collections.abc import Callable, Iterable, Sequence
from datetime import UTC, datetime, timedelta, timezone
from uuid import UUID, uuid4

from app.core.errors import ApiError
from app.features.action_center.models import (
    LINKS,
    SOURCE_LABELS,
    HomeSummary,
    NotificationEvent,
    NotificationPage,
    NotificationRecord,
    NotificationView,
    SourceType,
    SummaryItem,
)
from app.features.action_center.ports import SourceRef, Store, UnitOfWork
from app.features.campus import policy
from app.features.campus.domain import NoticeStatus
from app.features.notice_discussion.ports import CurrentAccess
from app.schemas.common import ErrorCode, utc_now

# Demo display day only (Korea has no DST); not an institutional calendar policy.
LOCAL = timezone(timedelta(hours=9))
SECTION_LIMIT = 10
NOTICE_LIMIT = 5
NOTICE_SCAN = 20
UNREAD_SCAN = 100
TASK_WINDOW = timedelta(days=7)
DEADLINE_WINDOW = timedelta(days=14)
INBOX_STATUSES = frozenset({NoticeStatus.PUBLISHED, NoticeStatus.ARCHIVED})


def view(row: NotificationRecord) -> NotificationView:
    return NotificationView(
        **row.model_dump(exclude={"recipient_id", "event_key"}), link=LINKS[row.source_type]
    )


class ActionCenterService:
    def __init__(self, store: Store, clock: Callable[[], datetime] = utc_now):
        self.store, self.clock = store, clock

    def _now(self) -> datetime:
        now = self.clock()
        if now.tzinfo is None or now.utcoffset() is None:
            raise ApiError(ErrorCode.UNAVAILABLE)
        return now.astimezone(UTC)

    @staticmethod
    def _access(uow: UnitOfWork, actor_id: UUID) -> CurrentAccess:
        current = uow.current_access()
        if current is None or not current.active or current.actor.user_id != actor_id:
            raise ApiError(ErrorCode.UNAUTHORIZED)
        if not current.demo:
            raise ApiError(ErrorCode.FORBIDDEN)
        return current

    @staticmethod
    def _items(
        rows: Sequence[SourceRef], kind: SourceType, start: datetime, end: datetime
    ) -> list[SummaryItem]:
        # A provider that breaks the reference contract fails closed instead of being shown.
        picked: dict[UUID, SourceRef] = {}
        for ref in rows:
            if (
                ref.source_type is not kind
                or ref.at.tzinfo is None
                or ref.record_source not in SOURCE_LABELS
                or (kind is SourceType.NOTICE) != (ref.record_source == "PLATFORM")
            ):
                raise ApiError(ErrorCode.UNAVAILABLE)
            if start <= ref.at < end:
                picked.setdefault(ref.source_id, ref)
        ordered = sorted(picked.values(), key=lambda r: (r.at, str(r.source_id)))
        try:
            return [
                SummaryItem(
                    source_type=kind,
                    source_id=r.source_id,
                    title=r.title.strip()[:200],
                    at=r.at.astimezone(UTC),
                    link=LINKS[kind],
                    record_source=r.record_source,
                )
                for r in ordered[:SECTION_LIMIT]
            ]
        except ValueError:
            raise ApiError(ErrorCode.UNAVAILABLE) from None

    @staticmethod
    def _visible(
        uow: UnitOfWork, access: CurrentAccess, rows: Iterable[NotificationRecord]
    ) -> list[NotificationRecord]:
        rows = list(rows)
        notice_ids = [r.source_id for r in rows if r.source_type is SourceType.NOTICE]
        notices = uow.notices.get_many(notice_ids) if notice_ids else {}
        shown = []
        for row in rows:
            if row.recipient_id != access.actor.user_id:
                continue
            if row.source_type is SourceType.NOTICE:
                notice = notices.get(row.source_id)
                ok = (
                    notice is not None
                    and notice.status in INBOX_STATUSES
                    and policy.can_read_notice(access.actor, notice)
                )
            else:
                ok = uow.sources.is_visible(row.source_type, row.source_id)
            if ok:
                shown.append(row)
        return shown

    def _unread(self, uow: UnitOfWork, access: CurrentAccess) -> tuple[int, bool]:
        raw = uow.list_unread(UNREAD_SCAN)
        unread = [r for r in self._visible(uow, access, raw[:UNREAD_SCAN]) if r.read_at is None]
        return len(unread), len(raw) >= UNREAD_SCAN

    def summary(self, actor_id: UUID) -> HomeSummary:
        now = self._now()
        local = now.astimezone(LOCAL)
        day_start = datetime(local.year, local.month, local.day, tzinfo=LOCAL).astimezone(UTC)
        day_end = day_start + timedelta(days=1)
        with self.store.unit_of_work(actor_id) as uow:
            access = self._access(uow, actor_id)
            src = uow.sources
            classes = self._items(
                src.classes_between(day_start, day_end, SECTION_LIMIT),
                SourceType.CLASS_SESSION,
                day_start,
                day_end,
            )
            tasks = self._items(
                src.tasks_due_between(now, now + TASK_WINDOW, SECTION_LIMIT),
                SourceType.TASK,
                now,
                now + TASK_WINDOW,
            )
            deadlines = self._items(
                src.deadlines_between(now, now + DEADLINE_WINDOW, SECTION_LIMIT),
                SourceType.OPPORTUNITY_DEADLINE,
                now,
                now + DEADLINE_WINDOW,
            )
            released = uow.notices.list_released_for(
                policy.actor_audiences(access.actor), NOTICE_SCAN
            )
            readable = [
                n
                for n in released[:NOTICE_SCAN]
                if n.status is NoticeStatus.PUBLISHED and policy.can_read_notice(access.actor, n)
            ]
            readable.sort(key=lambda n: (n.published_at or n.updated_at, str(n.id)), reverse=True)
            notices = [
                SummaryItem(
                    source_type=SourceType.NOTICE,
                    source_id=n.id,
                    title=n.title.strip()[:200] or "제목 없음",
                    at=(n.published_at or n.updated_at).astimezone(UTC),
                    link=LINKS[SourceType.NOTICE],
                    record_source="PLATFORM",
                )
                for n in readable[:NOTICE_LIMIT]
            ]
            unread, capped = self._unread(uow, access)
            return HomeSummary(
                local_date=local.date(),
                window_start=day_start,
                window_end=day_end,
                classes=classes,
                tasks=tasks,
                notices=notices,
                deadlines=deadlines,
                unread_notifications=unread,
                unread_capped=capped,
            )

    def inbox(self, actor_id: UUID, offset: int = 0, limit: int = 20) -> NotificationPage:
        if offset < 0 or not 1 <= limit <= 50:
            raise ApiError(ErrorCode.VALIDATION)
        with self.store.unit_of_work(actor_id) as uow:
            access = self._access(uow, actor_id)
            raw = list(uow.list_notifications(offset, limit))[:limit]
            return NotificationPage(
                items=[view(r) for r in self._visible(uow, access, raw)],
                offset=offset,
                limit=limit,
                next_offset=offset + len(raw) if len(raw) == limit else None,
            )

    def mark_read(
        self, actor_id: UUID, notification_id: UUID, expected_revision: int
    ) -> NotificationView:
        now = self._now()
        with self.store.unit_of_work(actor_id) as uow:
            access = self._access(uow, actor_id)
            row = uow.get_notification(notification_id)
            if row is None or not self._visible(uow, access, [row]):
                raise ApiError(ErrorCode.NOT_FOUND)
            if row.read_at is not None:
                return view(row)  # Replay of a completed read is a no-op.
            if row.revision != expected_revision:
                raise ApiError(ErrorCode.CONFLICT)
            updated = row.model_copy(update={"read_at": now, "revision": row.revision + 1})
            if not uow.mark_read(updated, expected_revision):
                raise ApiError(ErrorCode.CONFLICT)
            return view(updated)

    def deliver(self, event: NotificationEvent) -> NotificationView | None:
        """System consumer entry point; not routed. None means intentionally not delivered."""
        if (event.source_type is SourceType.NOTICE) != (event.record_source == "PLATFORM"):
            raise ApiError(ErrorCode.VALIDATION)
        now = self._now()
        with self.store.unit_of_work(event.recipient_id) as uow:
            access = uow.current_access()
            if (
                access is None
                or not access.active
                or not access.demo
                or access.actor.user_id != event.recipient_id
            ):
                return None
            probe = NotificationRecord(id=uuid4(), created_at=now, revision=1, **event.model_dump())
            existing = uow.find_notification(probe.dedupe_key)
            # Re-check the original even on replay so revoked access never resurfaces a row.
            if not self._visible(uow, access, [existing or probe]):
                return None
            if existing is not None:
                return view(existing)
            uow.insert_notification(probe)
            return view(probe)
