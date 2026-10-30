"""Delivery defense with existing test-only stores; no persistent notice/role provisioning."""

from dataclasses import replace

import pytest
from test_campus_support import DEPT_A, DEPT_B, World, assistant, student

from app.features.campus.domain import (
    Audience,
    AudienceType,
    CampusActor,
    ChannelKind,
    NoticeStatus,
)
from app.features.campus.services import ChatService, NoticeService


@pytest.mark.parametrize("mismatch", ["department", "grade", "kind", "all_grade", "bool_grade"])
def test_invalid_resolved_channel_never_receives_card_and_corrected_retry_is_idempotent(mismatch):
    world = World()
    grade = None if mismatch == "all_grade" else 1
    audience = Audience(
        AudienceType.DEPARTMENT if grade is None else AudienceType.DEPARTMENT_GRADE,
        DEPT_A,
        grade,
    )
    actor = CampusActor(assistant(DEPT_A, 1).user_id, (), frozenset({audience}))
    expected = world.a_all if grade is None else world.a_1
    wrong = {
        "department": replace(expected, department_id=DEPT_B),
        "grade": replace(expected, grade=2),
        "kind": replace(expected, kind=ChannelKind.DEPARTMENT_ALL),
        "all_grade": replace(expected, grade=1),
        "bool_grade": replace(expected, grade=True),
    }[mismatch]
    original_lookup = world.channels.find_default_channel
    world.channels.find_default_channel = lambda _department, _grade: wrong
    service = NoticeService(world.notices, world.channels, world.messages, world.clock)
    draft = service.create_draft(actor, audience, "Synthetic v1", "Synthetic body")
    notice, delivered = service.publish(actor, draft.id, 1)
    assert notice.status is NoticeStatus.PUBLISHED  # Publishing and delivery remain separate.
    assert delivered.channel_ids == () and delivered.created_count == 0
    assert [(target.department_id, target.grade) for target in delivered.missing_targets] == [
        (DEPT_A, grade)
    ]
    assert world.messages.rows == []

    # Failed attempts remain retryable, without changing or cloning the authoritative notice.
    service.deliver(draft.id)
    assert world.messages.rows == []
    revised = service.revise(actor, draft.id, "Synthetic v2", "Updated body", 1)
    world.channels.find_default_channel = original_lookup
    first, second = service.deliver(draft.id), service.deliver(draft.id)
    assert first.channel_ids == second.channel_ids == (expected.id,)
    assert (first.created_count, second.created_count) == (1, 0)
    assert first.missing_targets == second.missing_targets == ()
    assert len(world.messages.rows) == 1
    stored = world.messages.rows[0]
    assert stored.reference_notice_id == draft.id and stored.body is None
    chat = ChatService(world.channels, world.messages, world.notices, world.clock)
    card = chat.list_messages(student(DEPT_A, 1), expected.id, None, 10).items[0]
    assert card.notice == revised and card.notice.revision == 2


def test_archived_notice_retry_never_creates_a_new_card_after_missing_channel():
    from app.core.errors import ApiError
    from app.schemas.common import ErrorCode

    world = World()
    original_lookup = world.channels.find_default_channel
    world.channels.find_default_channel = lambda _department, _grade: None
    actor = assistant(DEPT_A, 2)
    service = NoticeService(world.notices, world.channels, world.messages, world.clock)
    draft = service.create_draft(
        actor, Audience(AudienceType.DEPARTMENT_GRADE, DEPT_A, 2), "Synthetic", "Body"
    )
    service.publish(actor, draft.id, 1)
    service.archive(actor, draft.id, 1)
    world.channels.find_default_channel = original_lookup
    with pytest.raises(ApiError) as error:
        service.deliver(draft.id)
    assert error.value.code is ErrorCode.CONFLICT
    assert world.messages.rows == []
