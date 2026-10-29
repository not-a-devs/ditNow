"""Campus services. Every method re-checks authorization; routers never decide access."""

import re
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime
from urllib.parse import urlsplit
from uuid import UUID, uuid4

from app.core.errors import ApiError
from app.features.campus import policy
from app.features.campus.domain import (
    AcademicEvent,
    AcademicTerm,
    Audience,
    CampusActor,
    Channel,
    ChatMessage,
    DeliveryResult,
    MessageKind,
    Notice,
    NoticeStatus,
    SourceKind,
)
from app.features.campus.repositories import (
    AcademicCalendarRepository,
    ChannelRepository,
    MessageRepository,
    NoticeRepository,
)
from app.schemas.common import ErrorCode

type Clock = Callable[[], datetime]

MESSAGE_MAX_LENGTH = 2000
NOTICE_TITLE_MAX_LENGTH = 200
NOTICE_BODY_MAX_LENGTH = 10000
MESSAGE_PAGE_MAX = 100
NOTICE_PAGE_MAX = 50
CALENDAR_RANGE_MAX_DAYS = 366
SOURCE_URL_MAX_LENGTH = 2048
CLIENT_NONCE_PATTERN = re.compile(r"^[A-Za-z0-9_-]{8,64}$")


def system_clock() -> datetime:
    return datetime.now(UTC)


def _reject() -> ApiError:
    return ApiError(ErrorCode.VALIDATION)


def clean_text(value: str, max_length: int, *, multiline: bool) -> str:
    """Trim and reject empty, oversized, or control-character input (newline/tab if multiline)."""
    text = value.strip()
    if not text or len(text) > max_length:
        raise _reject()
    allowed = {"\n", "\t"} if multiline else set()
    for character in text:
        if character in allowed:
            continue
        if unicodedata.category(character) in {"Cc", "Cf", "Cs"} and character != "‍":
            raise _reject()
    return text


def check_page_size(limit: int, maximum: int) -> int:
    if not 1 <= limit <= maximum:
        raise _reject()
    return limit


@dataclass(frozen=True, slots=True)
class MessageView:
    message: ChatMessage
    is_mine: bool
    notice: Notice | None


@dataclass(frozen=True, slots=True)
class MessagePage:
    items: list[MessageView]
    next_before: int | None


class ChatService:
    def __init__(
        self,
        channels: ChannelRepository,
        messages: MessageRepository,
        notices: NoticeRepository,
        clock: Clock = system_clock,
    ) -> None:
        self._channels = channels
        self._messages = messages
        self._notices = notices
        self._clock = clock

    def list_department_channels(self, actor: CampusActor, department_id: UUID) -> list[Channel]:
        if not policy.belongs_to_department(actor, department_id):
            raise ApiError(ErrorCode.FORBIDDEN)
        return policy.visible_channels(
            actor, self._channels.list_department_channels(department_id)
        )

    def _accessible_channel(self, actor: CampusActor, channel_id: UUID) -> Channel:
        channel = self._channels.get_channel(channel_id)
        if channel is None:
            raise ApiError(ErrorCode.NOT_FOUND)
        if not policy.can_access_channel(actor, channel):
            raise ApiError(ErrorCode.FORBIDDEN)
        return channel

    def list_messages(
        self, actor: CampusActor, channel_id: UUID, before: int | None, limit: int
    ) -> MessagePage:
        check_page_size(limit, MESSAGE_PAGE_MAX)
        if before is not None and before < 1:
            raise _reject()
        self._accessible_channel(actor, channel_id)
        rows = list(self._messages.list_messages(channel_id, before, limit))
        refs = [m.reference_notice_id for m in rows if m.reference_notice_id is not None]
        notices = self._notices.get_many(refs) if refs else {}
        items = []
        for message in rows:
            notice = None
            if message.reference_notice_id is not None:
                found = notices.get(message.reference_notice_id)
                # Card resolves the single original at read time; unreadable originals stay hidden.
                if found is not None and policy.can_read_notice(actor, found):
                    notice = found
            items.append(MessageView(message, message.author_id == actor.user_id, notice))
        next_before = rows[-1].seq if len(rows) == limit else None
        return MessagePage(items, next_before)

    def send_message(
        self, actor: CampusActor, channel_id: UUID, body: str, client_nonce: str
    ) -> tuple[MessageView, bool]:
        text = clean_text(body, MESSAGE_MAX_LENGTH, multiline=True)
        if not CLIENT_NONCE_PATTERN.fullmatch(client_nonce):
            raise _reject()
        self._accessible_channel(actor, channel_id)
        message, created = self._messages.insert_text(
            channel_id, actor.user_id, text, client_nonce, self._clock()
        )
        if not created and (message.body != text or message.kind is not MessageKind.TEXT):
            # Same nonce reused for different content: refuse instead of silently dropping.
            raise ApiError(ErrorCode.CONFLICT)
        return MessageView(message, True, None), created


class NoticeService:
    def __init__(
        self,
        notices: NoticeRepository,
        channels: ChannelRepository,
        messages: MessageRepository,
        clock: Clock = system_clock,
    ) -> None:
        self._notices = notices
        self._channels = channels
        self._messages = messages
        self._clock = clock

    def _managed(self, actor: CampusActor, notice_id: UUID) -> Notice:
        notice = self._notices.get(notice_id)
        if notice is None:
            raise ApiError(ErrorCode.NOT_FOUND)
        if not policy.can_author(actor, notice.audience):
            # Non-authors cannot learn whether a draft exists.
            if notice.status is NoticeStatus.DRAFT:
                raise ApiError(ErrorCode.NOT_FOUND)
            raise ApiError(ErrorCode.FORBIDDEN)
        return notice

    def create_draft(self, actor: CampusActor, audience: Audience, title: str, body: str) -> Notice:
        clean_title = clean_text(title, NOTICE_TITLE_MAX_LENGTH, multiline=False)
        clean_body = clean_text(body, NOTICE_BODY_MAX_LENGTH, multiline=True)
        if not policy.can_author(actor, audience):
            raise ApiError(ErrorCode.FORBIDDEN)
        now = self._clock()
        return self._notices.create(
            Notice(
                id=uuid4(),
                audience=audience,
                title=clean_title,
                body=clean_body,
                status=NoticeStatus.DRAFT,
                revision=1,
                author_id=actor.user_id,
                created_at=now,
                updated_at=now,
            )
        )

    def get(self, actor: CampusActor, notice_id: UUID) -> Notice:
        notice = self._notices.get(notice_id)
        if notice is None:
            raise ApiError(ErrorCode.NOT_FOUND)
        if policy.can_read_notice(actor, notice):
            return notice
        if notice.status is NoticeStatus.DRAFT:
            raise ApiError(ErrorCode.NOT_FOUND)
        raise ApiError(ErrorCode.FORBIDDEN)

    def list_for(self, actor: CampusActor, limit: int) -> list[Notice]:
        check_page_size(limit, NOTICE_PAGE_MAX)
        audiences = policy.actor_audiences(actor)
        if not audiences:
            return []
        rows = self._notices.list_released_for(audiences, limit)
        # Defense in depth: never trust the repository filter alone.
        return [
            n
            for n in rows
            if n.status is not NoticeStatus.DRAFT and policy.can_read_notice(actor, n)
        ]

    def revise(
        self,
        actor: CampusActor,
        notice_id: UUID,
        title: str,
        body: str,
        expected_revision: int,
    ) -> Notice:
        clean_title = clean_text(title, NOTICE_TITLE_MAX_LENGTH, multiline=False)
        clean_body = clean_text(body, NOTICE_BODY_MAX_LENGTH, multiline=True)
        notice = self._managed(actor, notice_id)
        if notice.status is NoticeStatus.ARCHIVED or notice.revision != expected_revision:
            raise ApiError(ErrorCode.CONFLICT)
        saved = self._notices.save_revision(
            notice_id, expected_revision, notice.status, clean_title, clean_body, self._clock()
        )
        if saved is None:
            raise ApiError(ErrorCode.CONFLICT)
        return saved

    def publish(
        self, actor: CampusActor, notice_id: UUID, expected_revision: int
    ) -> tuple[Notice, DeliveryResult]:
        """Publish exactly the revision the author reviewed; any concurrent change is 409."""
        notice = self._managed(actor, notice_id)
        if notice.status is NoticeStatus.ARCHIVED or notice.revision != expected_revision:
            raise ApiError(ErrorCode.CONFLICT)
        if notice.status is NoticeStatus.DRAFT:
            moved = self._notices.transition(
                notice_id,
                NoticeStatus.DRAFT,
                NoticeStatus.PUBLISHED,
                expected_revision,
                self._clock(),
            )
            if moved is None:
                # Only a concurrent publish of the same revision counts as success.
                current = self._notices.get(notice_id)
                if (
                    current is None
                    or current.status is not NoticeStatus.PUBLISHED
                    or current.revision != expected_revision
                ):
                    raise ApiError(ErrorCode.CONFLICT)
                moved = current
            notice = moved
        # Publishing an already published notice re-runs idempotent delivery only.
        return notice, self.deliver(notice_id)

    def deliver(self, notice_id: UUID) -> DeliveryResult:
        """System/outbox consumer. Safe to call repeatedly; one card per channel."""
        notice = self._notices.get(notice_id)
        if notice is None or notice.status is not NoticeStatus.PUBLISHED:
            raise ApiError(ErrorCode.CONFLICT)
        channel_ids: list[UUID] = []
        missing = []
        created_count = 0
        for target in policy.delivery_targets(notice.audience):
            channel = self._channels.find_default_channel(target.department_id, target.grade)
            if channel is None:
                # Kept separate from publish so a retry can complete it later.
                missing.append(target)
                continue
            _, created = self._messages.ensure_notice_card(channel.id, notice.id, self._clock())
            channel_ids.append(channel.id)
            created_count += int(created)
        return DeliveryResult(tuple(channel_ids), created_count, tuple(missing))

    def archive(self, actor: CampusActor, notice_id: UUID, expected_revision: int) -> Notice:
        notice = self._managed(actor, notice_id)
        if notice.revision != expected_revision:
            raise ApiError(ErrorCode.CONFLICT)
        if notice.status is NoticeStatus.ARCHIVED:
            # Repeating the same archive is idempotent.
            return notice
        moved = self._notices.transition(
            notice_id, notice.status, NoticeStatus.ARCHIVED, expected_revision, self._clock()
        )
        if moved is None:
            current = self._notices.get(notice_id)
            if (
                current is None
                or current.status is not NoticeStatus.ARCHIVED
                or current.revision != expected_revision
            ):
                raise ApiError(ErrorCode.CONFLICT)
            moved = current
        return moved


def safe_source_url(value: str | None) -> str | None:
    """Absolute http(s) URL with a host and no credentials/whitespace/control chars, else None."""
    if value is None or len(value) > SOURCE_URL_MAX_LENGTH:
        return None
    if any(c.isspace() or unicodedata.category(c) in {"Cc", "Cf", "Cs"} for c in value):
        return None
    try:
        parts = urlsplit(value)
        host = parts.hostname
    except ValueError:
        return None
    if parts.scheme not in {"http", "https"} or not host or "@" in parts.netloc:
        return None
    return value


def cited[R: (AcademicTerm, AcademicEvent)](record: R) -> R:
    """Fail closed on provenance.

    OFFICIAL_PUBLIC survives only with a safe http(s) URL and an aware checked_at; otherwise it
    is downgraded to UNKNOWN. Non-official records never carry a link or check time, so a demo
    or legacy row cannot borrow an official page's credibility.
    """
    if record.source_kind is SourceKind.OFFICIAL_PUBLIC:
        url = safe_source_url(record.source_url)
        checked = record.checked_at
        if url is not None and checked is not None and checked.tzinfo is not None:
            return record
        return replace(record, source_kind=SourceKind.UNKNOWN, source_url=None, checked_at=None)
    if record.source_url is None and record.checked_at is None:
        return record
    return replace(record, source_url=None, checked_at=None)


class AcademicService:
    """FR-ACA-001 read-only calendar. Records are DEMO, UNKNOWN, or cited OFFICIAL_PUBLIC."""

    def __init__(self, calendar: AcademicCalendarRepository) -> None:
        self._calendar = calendar

    def list_terms(self, actor: CampusActor) -> list[AcademicTerm]:
        del actor  # Authenticated read; no per-user academic record is exposed.
        terms = [cited(term) for term in self._calendar.list_terms()]
        return sorted(terms, key=lambda term: term.starts_on, reverse=True)

    def list_events(
        self,
        actor: CampusActor,
        term_id: UUID,
        from_date: date | None = None,
        to_date: date | None = None,
    ) -> tuple[AcademicTerm, list[AcademicEvent]]:
        del actor
        if from_date is not None and to_date is not None:
            if from_date > to_date or (to_date - from_date).days > CALENDAR_RANGE_MAX_DAYS:
                raise _reject()
        term = self._calendar.get_term(term_id)
        if term is None:
            raise ApiError(ErrorCode.NOT_FOUND)
        events = [
            cited(event)
            for event in self._calendar.list_events(term_id)
            if event.term_id == term_id
            and (from_date is None or event.ends_on >= from_date)
            and (to_date is None or event.starts_on <= to_date)
        ]
        events.sort(key=lambda event: (event.starts_on, event.title))
        return cited(term), events
