"""Test-only in-memory fakes for campus repository protocols. Not a production store."""

from collections.abc import Sequence
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from uuid import UUID, uuid4

from app.features.campus.domain import (
    AcademicEvent,
    AcademicTerm,
    Audience,
    AudienceType,
    CampusActor,
    Channel,
    ChannelKind,
    ChatMessage,
    Membership,
    MessageKind,
    Notice,
    NoticeStatus,
    SourceKind,
)

DEPT_A = UUID("00000000-0000-4000-8000-00000000000a")
DEPT_B = UUID("00000000-0000-4000-8000-00000000000b")


class FakeClock:
    def __init__(self) -> None:
        self.now = datetime(2026, 10, 30, 9, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        self.now += timedelta(seconds=1)
        return self.now


class FakeChannels:
    def __init__(self, channels: Sequence[Channel]) -> None:
        self.rows = {c.id: c for c in channels}

    def get_channel(self, channel_id: UUID) -> Channel | None:
        return self.rows.get(channel_id)

    def list_department_channels(self, department_id: UUID) -> list[Channel]:
        return [c for c in self.rows.values() if c.department_id == department_id]

    def find_default_channel(self, department_id: UUID, grade: int | None) -> Channel | None:
        for channel in self.rows.values():
            if channel.department_id == department_id and channel.grade == grade:
                return channel
        return None


class FakeMessages:
    def __init__(self) -> None:
        self.rows: list[ChatMessage] = []

    def _next(self, **fields) -> ChatMessage:
        message = ChatMessage(id=uuid4(), seq=len(self.rows) + 1, **fields)
        self.rows.append(message)
        return message

    def insert_text(self, channel_id, author_id, body, client_nonce, created_at):
        for row in self.rows:
            if (row.channel_id, row.author_id, row.client_nonce) == (
                channel_id,
                author_id,
                client_nonce,
            ):
                return row, False
        message = self._next(
            channel_id=channel_id,
            kind=MessageKind.TEXT,
            created_at=created_at,
            author_id=author_id,
            body=body,
            client_nonce=client_nonce,
        )
        return message, True

    def ensure_notice_card(self, channel_id, notice_id, created_at):
        for row in self.rows:
            if row.channel_id == channel_id and row.reference_notice_id == notice_id:
                return row, False
        message = self._next(
            channel_id=channel_id,
            kind=MessageKind.NOTICE_CARD,
            created_at=created_at,
            reference_notice_id=notice_id,
        )
        return message, True

    def list_messages(self, channel_id, before_seq, limit):
        rows = [
            r
            for r in self.rows
            if r.channel_id == channel_id and (before_seq is None or r.seq < before_seq)
        ]
        return sorted(rows, key=lambda r: r.seq, reverse=True)[:limit]


class FakeNotices:
    def __init__(self) -> None:
        self.rows: dict[UUID, Notice] = {}
        # Runs once just before the next conditional write, simulating another writer that
        # committed between the service's read and its compare-and-set.
        self.interleave = None

    def _race(self) -> None:
        hook, self.interleave = self.interleave, None
        if hook is not None:
            hook()

    def get(self, notice_id):
        return self.rows.get(notice_id)

    def get_many(self, notice_ids):
        return {i: self.rows[i] for i in notice_ids if i in self.rows}

    def create(self, notice):
        self.rows[notice.id] = notice
        return notice

    def save_revision(self, notice_id, expected_revision, expected_status, title, body, at):
        self._race()
        current = self.rows.get(notice_id)
        if (
            current is None
            or current.revision != expected_revision
            or current.status is not expected_status
        ):
            return None
        saved = replace(
            current, title=title, body=body, revision=expected_revision + 1, updated_at=at
        )
        self.rows[notice_id] = saved
        return saved

    def transition(self, notice_id, from_status, to_status, expected_revision, at):
        self._race()
        current = self.rows.get(notice_id)
        if (
            current is None
            or current.status is not from_status
            or current.revision != expected_revision
        ):
            return None
        published_at = at if to_status is NoticeStatus.PUBLISHED else current.published_at
        moved = replace(current, status=to_status, updated_at=at, published_at=published_at)
        self.rows[notice_id] = moved
        return moved

    def list_released_for(self, audiences, limit):
        wanted = set(audiences)
        rows = [
            n
            for n in self.rows.values()
            if n.status is not NoticeStatus.DRAFT and n.audience in wanted
        ]
        return sorted(rows, key=lambda n: n.updated_at, reverse=True)[:limit]


class FakeCalendar:
    def __init__(self, terms, events) -> None:
        self.terms = list(terms)
        self.events = list(events)

    def list_terms(self):
        return self.terms

    def get_term(self, term_id):
        return next((t for t in self.terms if t.id == term_id), None)

    def list_events(self, term_id):
        return [e for e in self.events if e.term_id == term_id]


def channel(department_id: UUID, grade: int | None) -> Channel:
    kind = ChannelKind.DEPARTMENT_ALL if grade is None else ChannelKind.DEPARTMENT_GRADE
    return Channel(uuid4(), department_id, kind, f"demo-{grade or 'all'}", grade)


def student(department_id: UUID, grade: int) -> CampusActor:
    return CampusActor(uuid4(), (Membership(department_id, grade),))


def assistant(department_id: UUID, grade: int) -> CampusActor:
    scope = Audience(AudienceType.DEPARTMENT_GRADE, department_id, grade)
    return CampusActor(uuid4(), (Membership(department_id, None),), frozenset({scope}))


class World:
    """Demo-only fixture: two departments with all + grade 1/2 channels. No real data."""

    def __init__(self) -> None:
        self.clock = FakeClock()
        self.a_all = channel(DEPT_A, None)
        self.a_1 = channel(DEPT_A, 1)
        self.a_2 = channel(DEPT_A, 2)
        self.b_all = channel(DEPT_B, None)
        self.b_2 = channel(DEPT_B, 2)
        self.channels = FakeChannels([self.a_all, self.a_1, self.a_2, self.b_all, self.b_2])
        self.messages = FakeMessages()
        self.notices = FakeNotices()
        self.term = AcademicTerm(
            uuid4(), "가상 2026-2학기", date(2026, 9, 1), date(2027, 2, 28), SourceKind.DEMO
        )
        self.old_term = AcademicTerm(
            uuid4(), "가상 2026-1학기", date(2026, 3, 1), date(2026, 8, 31), SourceKind.DEMO
        )
        self.events = [
            AcademicEvent(
                uuid4(),
                self.term.id,
                "가상 중간고사",
                date(2026, 10, 20),
                date(2026, 10, 24),
                SourceKind.DEMO,
            ),
            AcademicEvent(
                uuid4(),
                self.term.id,
                "가상 개강",
                date(2026, 9, 1),
                date(2026, 9, 1),
                SourceKind.DEMO,
            ),
            AcademicEvent(
                uuid4(),
                self.old_term.id,
                "가상 1학기 기말",
                date(2026, 6, 15),
                date(2026, 6, 19),
                SourceKind.DEMO,
            ),
        ]
        self.calendar = FakeCalendar([self.old_term, self.term], self.events)
