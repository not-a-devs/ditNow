"""Service behavior with test-only fakes.

TC-V1-DEPT-001/002/005, TC-V1-NOT-001/002, TC-V1-ACA-001.
"""

from dataclasses import replace
from datetime import UTC, date, datetime
from uuid import uuid4

import pytest
from test_campus_support import DEPT_A, DEPT_B, FakeCalendar, World, assistant, student

from app.core.errors import ApiError
from app.features.campus.domain import (
    AcademicEvent,
    Audience,
    AudienceType,
    CampusActor,
    MessageKind,
    NoticeStatus,
    SourceKind,
)
from app.features.campus.services import (
    AcademicService,
    ChatService,
    NoticeService,
    safe_source_url,
)
from app.schemas.common import ErrorCode

GRADE2 = Audience(AudienceType.DEPARTMENT_GRADE, DEPT_A, 2)


@pytest.fixture
def world():
    return World()


def chat(world: World) -> ChatService:
    return ChatService(world.channels, world.messages, world.notices, world.clock)


def notices(world: World) -> NoticeService:
    return NoticeService(world.notices, world.channels, world.messages, world.clock)


def code_of(call) -> ErrorCode:
    with pytest.raises(ApiError) as exc:
        call()
    return exc.value.code


# --- chat -----------------------------------------------------------------


def test_department_channel_listing_hides_other_grades(world):
    items = chat(world).list_department_channels(student(DEPT_A, 2), DEPT_A)
    assert {c.id for c in items} == {world.a_all.id, world.a_2.id}
    assert code_of(lambda: chat(world).list_department_channels(student(DEPT_B, 2), DEPT_A)) == (
        ErrorCode.FORBIDDEN
    )


def test_two_students_exchange_and_reload(world):
    a, b = student(DEPT_A, 2), student(DEPT_A, 2)
    service = chat(world)
    service.send_message(a, world.a_2.id, " 안녕하세요 ", "nonce-a-0001")
    service.send_message(b, world.a_2.id, "반가워요", "nonce-b-0001")
    page = service.list_messages(a, world.a_2.id, None, 50)
    assert [v.message.body for v in page.items] == ["반가워요", "안녕하세요"]
    assert [v.is_mine for v in page.items] == [False, True]
    assert page.next_before is None


def test_other_department_and_grade_denied(world):
    service = chat(world)
    for outsider in (student(DEPT_B, 2), student(DEPT_A, 1)):
        assert code_of(lambda o=outsider: service.list_messages(o, world.a_2.id, None, 10)) == (
            ErrorCode.FORBIDDEN
        )
        assert (
            code_of(lambda o=outsider: service.send_message(o, world.a_2.id, "x", "nonce-x-0001"))
            == ErrorCode.FORBIDDEN
        )
    assert world.messages.rows == []


def test_unknown_channel_is_not_found(world):
    assert code_of(lambda: chat(world).list_messages(student(DEPT_A, 2), uuid4(), None, 10)) == (
        ErrorCode.NOT_FOUND
    )


def test_client_nonce_dedupes_and_rejects_reuse(world):
    a = student(DEPT_A, 2)
    service = chat(world)
    first, created = service.send_message(a, world.a_2.id, "hello", "nonce-dup-01")
    again, created_again = service.send_message(a, world.a_2.id, "hello", "nonce-dup-01")
    assert created and not created_again
    assert first.message.id == again.message.id
    assert len(world.messages.rows) == 1
    assert code_of(lambda: service.send_message(a, world.a_2.id, "other", "nonce-dup-01")) == (
        ErrorCode.CONFLICT
    )


@pytest.mark.parametrize(
    ("body", "nonce"),
    [
        ("   ", "nonce-ok-0001"),
        ("x" * 2001, "nonce-ok-0001"),
        ("bad\x00byte", "nonce-ok-0001"),
        ("rtl‮override", "nonce-ok-0001"),
        ("ok", "short"),
        ("ok", "has space 0001"),
    ],
)
def test_message_input_validation(world, body, nonce):
    assert (
        code_of(lambda: chat(world).send_message(student(DEPT_A, 2), world.a_2.id, body, nonce))
        == ErrorCode.VALIDATION
    )


def test_message_pagination_cursor(world):
    a = student(DEPT_A, 2)
    service = chat(world)
    for index in range(5):
        service.send_message(a, world.a_2.id, f"m{index}", f"nonce-page-{index:02d}")
    first = service.list_messages(a, world.a_2.id, None, 2)
    assert [v.message.body for v in first.items] == ["m4", "m3"]
    second = service.list_messages(a, world.a_2.id, first.next_before, 2)
    assert [v.message.body for v in second.items] == ["m2", "m1"]
    assert code_of(lambda: service.list_messages(a, world.a_2.id, None, 101)) == (
        ErrorCode.VALIDATION
    )


# --- notices ----------------------------------------------------------------


def test_publish_creates_one_card_and_repeat_delivery_is_idempotent(world):
    ta = assistant(DEPT_A, 2)
    service = notices(world)
    draft = service.create_draft(ta, GRADE2, "가상 MT 안내", "본문")
    notice, first = service.publish(ta, draft.id, 1)
    assert notice.status is NoticeStatus.PUBLISHED and notice.published_at is not None
    assert first.channel_ids == (world.a_2.id,) and first.created_count == 1
    # Same publish event processed three times in total (TC-V1-NOT-002).
    _, second = service.publish(ta, draft.id, 1)
    third = service.deliver(draft.id)
    assert second.created_count == 0 and third.created_count == 0
    cards = [m for m in world.messages.rows if m.kind is MessageKind.NOTICE_CARD]
    assert len(cards) == 1 and cards[0].channel_id == world.a_2.id


def test_card_shows_latest_original_and_is_isolated(world):
    ta = assistant(DEPT_A, 2)
    service = notices(world)
    draft = service.create_draft(ta, GRADE2, "v1 제목", "본문")
    service.publish(ta, draft.id, 1)
    revised = service.revise(ta, draft.id, "v2 제목", "수정 본문", expected_revision=1)
    assert revised.revision == 2
    page = chat(world).list_messages(student(DEPT_A, 2), world.a_2.id, None, 10)
    card = page.items[0]
    assert card.notice is not None
    assert (card.notice.title, card.notice.revision) == ("v2 제목", 2)
    assert card.message.body is None
    # Other grade/department channels got nothing.
    assert all(m.channel_id == world.a_2.id for m in world.messages.rows)
    assert code_of(lambda: service.get(student(DEPT_B, 2), draft.id)) == ErrorCode.FORBIDDEN
    assert code_of(lambda: service.get(student(DEPT_A, 1), draft.id)) == ErrorCode.FORBIDDEN


def test_department_notice_goes_to_department_channel_and_school_to_none(world):
    scopes = frozenset({Audience(AudienceType.DEPARTMENT, DEPT_A), Audience(AudienceType.SCHOOL)})
    staff = CampusActor(assistant(DEPT_A, 2).user_id, (), scopes)
    service = notices(world)
    dept = service.create_draft(staff, Audience(AudienceType.DEPARTMENT, DEPT_A), "학과", "b")
    _, result = service.publish(staff, dept.id, 1)
    assert result.channel_ids == (world.a_all.id,)
    school = service.create_draft(staff, Audience(AudienceType.SCHOOL), "전체", "b")
    _, result = service.publish(staff, school.id, 1)
    assert result.channel_ids == () and result.created_count == 0


def test_missing_channel_is_reported_not_faked(world):
    scope = Audience(AudienceType.DEPARTMENT_GRADE, DEPT_B, 1)
    staff = CampusActor(assistant(DEPT_B, 1).user_id, (), frozenset({scope}))
    service = notices(world)
    draft = service.create_draft(staff, scope, "t", "b")
    notice, result = service.publish(staff, draft.id, 1)
    assert notice.status is NoticeStatus.PUBLISHED
    assert result.channel_ids == () and len(result.missing_targets) == 1


def test_students_and_out_of_scope_staff_cannot_author(world):
    service = notices(world)
    assert code_of(lambda: service.create_draft(student(DEPT_A, 2), GRADE2, "t", "b")) == (
        ErrorCode.FORBIDDEN
    )
    other = Audience(AudienceType.DEPARTMENT_GRADE, DEPT_B, 2)
    assert code_of(lambda: service.create_draft(assistant(DEPT_A, 2), other, "t", "b")) == (
        ErrorCode.FORBIDDEN
    )
    assert world.notices.rows == {}


def test_non_author_cannot_manage_and_drafts_are_hidden(world):
    ta = assistant(DEPT_A, 2)
    service = notices(world)
    draft = service.create_draft(ta, GRADE2, "t", "b")
    a2 = student(DEPT_A, 2)
    assert code_of(lambda: service.get(a2, draft.id)) == ErrorCode.NOT_FOUND
    assert code_of(lambda: service.publish(a2, draft.id, 1)) == ErrorCode.NOT_FOUND
    assert service.list_for(a2, 20) == []
    service.publish(ta, draft.id, 1)
    assert code_of(lambda: service.revise(a2, draft.id, "x", "y", 1)) == ErrorCode.FORBIDDEN
    assert code_of(lambda: service.archive(a2, draft.id, 1)) == ErrorCode.FORBIDDEN
    assert [n.id for n in service.list_for(a2, 20)] == [draft.id]
    assert service.list_for(student(DEPT_B, 2), 20) == []


def test_revision_conflict_and_archive_lifecycle(world):
    ta = assistant(DEPT_A, 2)
    service = notices(world)
    draft = service.create_draft(ta, GRADE2, "t", "b")
    service.revise(ta, draft.id, "t2", "b2", 1)
    assert code_of(lambda: service.revise(ta, draft.id, "t3", "b3", 1)) == ErrorCode.CONFLICT
    service.publish(ta, draft.id, 2)
    archived = service.archive(ta, draft.id, 2)
    assert archived.status is NoticeStatus.ARCHIVED
    assert service.archive(ta, draft.id, 2).status is NoticeStatus.ARCHIVED
    assert code_of(lambda: service.publish(ta, draft.id, 2)) == ErrorCode.CONFLICT
    assert code_of(lambda: service.revise(ta, draft.id, "t", "b", 2)) == ErrorCode.CONFLICT
    assert code_of(lambda: service.deliver(draft.id)) == ErrorCode.CONFLICT


# --- revision compare-and-set (publish/archive) ------------------------------------


def test_publish_and_archive_reject_stale_revision_without_side_effects(world):
    ta = assistant(DEPT_A, 2)
    service = notices(world)
    draft = service.create_draft(ta, GRADE2, "v1", "b")
    service.revise(ta, draft.id, "v2", "b2", 1)
    # Author reviewed v1; publishing it must not release v2 that they never saw.
    assert code_of(lambda: service.publish(ta, draft.id, 1)) == ErrorCode.CONFLICT
    assert world.notices.rows[draft.id].status is NoticeStatus.DRAFT
    assert world.messages.rows == []
    service.publish(ta, draft.id, 2)
    assert code_of(lambda: service.archive(ta, draft.id, 1)) == ErrorCode.CONFLICT
    assert world.notices.rows[draft.id].status is NoticeStatus.PUBLISHED


def test_revision_committed_between_read_and_publish_is_conflict(world):
    ta, other_editor = assistant(DEPT_A, 2), assistant(DEPT_A, 2)
    service = notices(world)
    draft = service.create_draft(ta, GRADE2, "v1", "b")
    world.notices.interleave = lambda: service.revise(other_editor, draft.id, "v2", "b2", 1)
    assert code_of(lambda: service.publish(ta, draft.id, 1)) == ErrorCode.CONFLICT
    stored = world.notices.rows[draft.id]
    assert (stored.status, stored.revision, stored.title) == (NoticeStatus.DRAFT, 2, "v2")
    assert world.messages.rows == []


def test_revision_committed_between_read_and_archive_is_conflict(world):
    ta, other_editor = assistant(DEPT_A, 2), assistant(DEPT_A, 2)
    service = notices(world)
    draft = service.create_draft(ta, GRADE2, "v1", "b")
    service.publish(ta, draft.id, 1)
    world.notices.interleave = lambda: service.revise(other_editor, draft.id, "v2", "b2", 1)
    assert code_of(lambda: service.archive(ta, draft.id, 1)) == ErrorCode.CONFLICT
    assert world.notices.rows[draft.id].status is NoticeStatus.PUBLISHED


def test_concurrent_archive_is_not_overwritten_by_revise(world):
    ta, other_editor = assistant(DEPT_A, 2), assistant(DEPT_A, 2)
    service = notices(world)
    draft = service.create_draft(ta, GRADE2, "v1", "b")
    service.publish(ta, draft.id, 1)
    world.notices.interleave = lambda: service.archive(other_editor, draft.id, 1)
    assert code_of(lambda: service.revise(ta, draft.id, "v2", "b2", 1)) == ErrorCode.CONFLICT
    stored = world.notices.rows[draft.id]
    assert (stored.status, stored.revision) == (NoticeStatus.ARCHIVED, 1)


def test_concurrent_publish_of_same_revision_is_idempotent(world):
    ta, other_editor = assistant(DEPT_A, 2), assistant(DEPT_A, 2)
    service = notices(world)
    draft = service.create_draft(ta, GRADE2, "v1", "b")
    world.notices.interleave = lambda: service.publish(other_editor, draft.id, 1)
    notice, _ = service.publish(ta, draft.id, 1)
    assert notice.status is NoticeStatus.PUBLISHED and notice.revision == 1
    assert len([m for m in world.messages.rows if m.kind is MessageKind.NOTICE_CARD]) == 1


def test_card_reflects_archive_and_stays_inside_audience(world):
    ta = assistant(DEPT_A, 2)
    service = notices(world)
    draft = service.create_draft(ta, GRADE2, "v1", "b")
    service.publish(ta, draft.id, 1)
    service.archive(ta, draft.id, 1)
    card = chat(world).list_messages(student(DEPT_A, 2), world.a_2.id, None, 10).items[0]
    assert card.notice is not None and card.notice.status is NoticeStatus.ARCHIVED
    # Leaving the grade (current membership re-read) hides the channel and the card.
    assert (
        code_of(lambda: chat(world).list_messages(student(DEPT_A, 3), world.a_2.id, None, 10))
        == ErrorCode.FORBIDDEN
    )


def test_notice_title_rejects_newline(world):
    assert (
        code_of(lambda: notices(world).create_draft(assistant(DEPT_A, 2), GRADE2, "a\nb", "body"))
        == ErrorCode.VALIDATION
    )


# --- academic -----------------------------------------------------------------


def test_academic_terms_and_events(world):
    service = AcademicService(world.calendar)
    a2 = student(DEPT_A, 2)
    assert [t.id for t in service.list_terms(a2)] == [world.term.id, world.old_term.id]
    term, events = service.list_events(a2, world.term.id)
    assert term.id == world.term.id
    assert [e.title for e in events] == ["가상 개강", "가상 중간고사"]
    _, ranged = service.list_events(a2, world.term.id, date(2026, 10, 1), date(2026, 10, 31))
    assert [e.title for e in ranged] == ["가상 중간고사"]


def test_academic_range_validation_and_unknown_term(world):
    service = AcademicService(world.calendar)
    a2 = student(DEPT_A, 2)
    assert (
        code_of(
            lambda: service.list_events(a2, world.term.id, date(2026, 11, 1), date(2026, 10, 1))
        )
        == ErrorCode.VALIDATION
    )
    assert (
        code_of(lambda: service.list_events(a2, world.term.id, date(2026, 1, 1), date(2027, 6, 1)))
        == ErrorCode.VALIDATION
    )
    assert code_of(lambda: service.list_events(a2, uuid4())) == ErrorCode.NOT_FOUND


# --- academic provenance (OFFICIAL_PUBLIC must be cited) -------------------------------

CHECKED = datetime(2026, 10, 1, 9, 0, tzinfo=UTC)
OFFICIAL_URL = "https://www.example.ac.kr/academic/calendar"


@pytest.mark.parametrize(
    "url",
    [
        "https://www.example.ac.kr/a?b=1",
        "http://example.ac.kr",
    ],
)
def test_safe_source_url_accepts_plain_http_urls(url):
    assert safe_source_url(url) == url


@pytest.mark.parametrize(
    "url",
    [
        "javascript:alert(1)",
        "JAVASCRIPT:alert(1)",
        "data:text/html,<b>x</b>",
        "vbscript:msgbox",
        "//example.ac.kr/path",
        "/relative/path",
        "https://",
        "https://user:pw@example.ac.kr/",
        "https://example.ac.kr/\nx",
        " https://example.ac.kr/",
        "https://exa mple.ac.kr/",
        "https://[::1/",
        "https://example.ac.kr/" + "a" * 2048,
        "",
    ],
)
def test_safe_source_url_rejects_unsafe_values(url):
    assert safe_source_url(url) is None


def _calendar_with(world: World, **fields) -> AcademicService:
    event = AcademicEvent(
        uuid4(), world.term.id, "공식 개강", date(2026, 9, 1), date(2026, 9, 1), **fields
    )
    return AcademicService(FakeCalendar([world.term], [event]))


@pytest.mark.parametrize(
    "fields",
    [
        {"source_url": "javascript:alert(1)", "checked_at": CHECKED},
        {"source_url": OFFICIAL_URL, "checked_at": None},
        {"source_url": None, "checked_at": CHECKED},
        {"source_url": OFFICIAL_URL, "checked_at": datetime(2026, 10, 1, 9, 0)},
    ],
)
def test_uncited_official_record_is_downgraded_to_unknown(world, fields):
    service = _calendar_with(world, source_kind=SourceKind.OFFICIAL_PUBLIC, **fields)
    _, (event,) = service.list_events(student(DEPT_A, 2), world.term.id)
    assert event.source_kind is SourceKind.UNKNOWN
    assert event.source_url is None and event.checked_at is None


def test_cited_official_record_keeps_source(world):
    service = _calendar_with(
        world, source_kind=SourceKind.OFFICIAL_PUBLIC, source_url=OFFICIAL_URL, checked_at=CHECKED
    )
    _, (event,) = service.list_events(student(DEPT_A, 2), world.term.id)
    assert (event.source_kind, event.source_url, event.checked_at) == (
        SourceKind.OFFICIAL_PUBLIC,
        OFFICIAL_URL,
        CHECKED,
    )


@pytest.mark.parametrize("kind", [SourceKind.DEMO, SourceKind.UNKNOWN])
def test_non_official_records_never_carry_a_link(world, kind):
    service = _calendar_with(world, source_kind=kind, source_url=OFFICIAL_URL, checked_at=CHECKED)
    _, (event,) = service.list_events(student(DEPT_A, 2), world.term.id)
    assert (event.source_kind, event.source_url, event.checked_at) == (kind, None, None)


def test_terms_are_normalized_too(world):
    bad = replace(world.term, source_kind=SourceKind.OFFICIAL_PUBLIC, source_url="javascript:x")
    service = AcademicService(FakeCalendar([bad], []))
    (term,) = service.list_terms(student(DEPT_A, 2))
    assert term.source_kind is SourceKind.UNKNOWN and term.source_url is None
    listed_term, _ = service.list_events(student(DEPT_A, 2), bad.id)
    assert listed_term.source_kind is SourceKind.UNKNOWN
