"""FR-DEPT-003/004 first pass: service rules on a serialized fake (TC-V1-DEPT-003/004 unit only).

Not a MariaDB, concurrency-under-InnoDB, global-app or E2E result.
"""

import threading

import pytest
from test_channels_support import (
    ALICE,
    BOB,
    CAROL,
    DAVE,
    DEFAULT_CHANNEL,
    DEPT,
    KEY,
    KEY2,
    NOBODY,
    OTHER_DEPT,
    make,
    new_channel,
    random_id,
)

from app.core.errors import ApiError
from app.features.campus.domain import Membership
from app.features.channels.domain import (
    MEMBER_LIMIT,
    OWNED_ACTIVE_LIMIT_PER_SCOPE,
    ChannelsActor,
    ChannelStatus,
    MemberRole,
    RequestStatus,
)
from app.schemas.common import ErrorCode

REASON = "학과 공식 학습 공동체로 운영하고 싶습니다."


def code(fn, *args):
    with pytest.raises(ApiError) as caught:
        fn(*args)
    return caught.value.code


# ---- create / scope ---------------------------------------------------------------------


def test_owner_creates_department_wide_channel_and_becomes_owner():
    service, store = make()
    result = service.create(ALICE, DEPT, None, "  알고리즘   스터디 ", "설명", KEY)
    view = result.value
    assert not result.replayed
    assert view.my_role is MemberRole.OWNER
    assert view.channel.name == "알고리즘 스터디"
    assert view.channel.member_count == 1
    assert view.channel.status is ChannelStatus.ACTIVE
    assert store.members[(view.channel.id, ALICE.user_id)].role is MemberRole.OWNER


@pytest.mark.parametrize(
    "actor,dept,grade",
    [
        (DAVE, DEPT, None),  # other department
        (CAROL, DEPT, 2),  # same department, other grade
        (NOBODY, DEPT, None),  # no current membership
        (ALICE, OTHER_DEPT, None),
    ],
)
def test_create_outside_current_scope_is_forbidden_and_writes_nothing(actor, dept, grade):
    service, store = make()
    assert code(service.create, actor, dept, grade, "스터디", "", KEY) is ErrorCode.FORBIDDEN
    assert not store.channels and not store.claims


def test_grade_scoped_channel_requires_exact_grade():
    service, _ = make()
    channel = new_channel(service, ALICE, grade=2).channel
    assert service.get(BOB, channel.id).my_role is None
    assert code(service.get, CAROL, channel.id) is ErrorCode.FORBIDDEN
    assert code(service.join, CAROL, channel.id) is ErrorCode.FORBIDDEN


def test_create_replay_returns_same_channel_and_different_payload_conflicts():
    service, store = make()
    first = service.create(ALICE, DEPT, None, "스터디 모임", "a", KEY)
    again = service.create(ALICE, DEPT, None, "스터디 모임", "a", KEY)
    assert again.replayed and again.value.channel.id == first.value.channel.id
    assert len(store.channels) == 1
    assert code(service.create, ALICE, DEPT, None, "스터디 모임", "b", KEY) is ErrorCode.CONFLICT
    # Same key for a different actor is a separate namespace, not a replay of Alice's channel.
    assert code(service.create, BOB, DEPT, None, "스터디 모임", "a", KEY) is ErrorCode.CONFLICT
    assert len(store.channels) == 1


def test_replay_after_revocation_is_forbidden():
    service, store = make()
    service.create(ALICE, DEPT, None, "스터디 모임", "a", KEY)
    store.memberships[ALICE.user_id] = (Membership(OTHER_DEPT, 2),)
    assert code(service.create, ALICE, DEPT, None, "스터디 모임", "a", KEY) is ErrorCode.FORBIDDEN


@pytest.mark.parametrize("name", ["Study", "ＳＴＵＤＹ", "study ", "s t u d y"])
def test_active_name_is_unique_per_scope_after_unicode_folding(name):
    service, _ = make()
    new_channel(service, ALICE, name="study")
    outcome = None
    try:
        service.create(BOB, DEPT, None, name, "", KEY2)
    except ApiError as error:
        outcome = error.code
    if name == "s t u d y":
        assert outcome is None  # different key; spacing inside words is significant
    else:
        assert outcome is ErrorCode.CONFLICT


def test_same_name_allowed_in_other_scope_and_after_archive():
    service, _ = make()
    channel = new_channel(service, ALICE, name="study").channel
    assert new_channel(service, ALICE, name="study", grade=2).channel.grade == 2
    service.archive(ALICE, channel.id, channel.revision)
    assert new_channel(service, BOB, name="study").channel.name == "study"


@pytest.mark.parametrize(
    "name",
    ["", "   ", "a" * 41, "bad‮name", "tab\tname", "line\nname", "zero​width", "\x00"],
)
def test_invalid_names_rejected(name):
    service, store = make()
    assert code(service.create, ALICE, DEPT, None, name, "", KEY) is ErrorCode.VALIDATION
    assert not store.channels


def test_unicode_names_are_nfc_and_counted_by_code_point():
    service, _ = make()
    decomposed = "가" * 39 + "가"  # 41 code points, NFC -> 40
    channel = new_channel(service, ALICE, name=decomposed).channel
    assert channel.name == "가" * 40
    emoji_family = "팀\U0001f468‍\U0001f469‍\U0001f467"
    assert new_channel(service, ALICE, name=emoji_family).channel.name == emoji_family


def test_owned_active_channel_limit_per_scope():
    service, _ = make()
    for index in range(OWNED_ACTIVE_LIMIT_PER_SCOPE):
        new_channel(service, ALICE, name=f"채널{index}")
    assert code(service.create, ALICE, DEPT, None, "하나 더", "", KEY) is ErrorCode.CONFLICT


# ---- default channels are authoritative -------------------------------------------------


@pytest.mark.parametrize("op", ["get", "update", "archive", "join", "leave", "request"])
def test_default_department_channel_cannot_be_managed_here(op):
    service, store = make()
    calls = {
        "get": lambda: service.get(ALICE, DEFAULT_CHANNEL),
        "update": lambda: service.update(ALICE, DEFAULT_CHANNEL, "이름", "", 1),
        "archive": lambda: service.archive(ALICE, DEFAULT_CHANNEL, 1),
        "join": lambda: service.join(ALICE, DEFAULT_CHANNEL),
        "leave": lambda: service.leave(ALICE, DEFAULT_CHANNEL),
        "request": lambda: service.request_official(ALICE, DEFAULT_CHANNEL, REASON, KEY),
    }
    assert code(calls[op]) is ErrorCode.FORBIDDEN
    assert not store.channels and not store.requests


# ---- owner management ---------------------------------------------------------------------


def test_owner_edits_with_cas_and_stale_revision_conflicts():
    service, _ = make()
    channel = new_channel(service).channel
    edited = service.update(ALICE, channel.id, "새 이름", "새 설명", channel.revision).channel
    assert edited.revision == channel.revision + 1 and edited.name == "새 이름"
    stale = service.update
    assert code(stale, ALICE, channel.id, "또 다른", "", channel.revision) is ErrorCode.CONFLICT
    assert service.get(ALICE, channel.id).channel.name == "새 이름"


def test_member_and_outsider_cannot_manage_or_request():
    service, _ = make()
    channel = new_channel(service).channel
    service.join(BOB, channel.id)
    for actor in (BOB, CAROL):
        assert code(service.update, actor, channel.id, "탈취", "", 1) is ErrorCode.FORBIDDEN
        assert code(service.archive, actor, channel.id, 1) is ErrorCode.FORBIDDEN
        failure = code(service.request_official, actor, channel.id, REASON, KEY)
        assert failure is ErrorCode.FORBIDDEN
    assert code(service.update, DAVE, channel.id, "탈취", "", 1) is ErrorCode.FORBIDDEN


def test_owner_who_lost_department_cannot_manage():
    service, store = make()
    channel = new_channel(service).channel
    store.memberships[ALICE.user_id] = (Membership(OTHER_DEPT, 2),)
    assert code(service.update, ALICE, channel.id, "x", "", 1) is ErrorCode.FORBIDDEN
    assert code(service.archive, ALICE, channel.id, 1) is ErrorCode.FORBIDDEN
    assert code(service.get, ALICE, channel.id) is ErrorCode.FORBIDDEN


def test_archive_is_cas_idempotent_and_blocks_join_and_edit():
    service, _ = make()
    channel = new_channel(service).channel
    archived = service.archive(ALICE, channel.id, channel.revision).channel
    assert archived.status is ChannelStatus.ARCHIVED and archived.archived_at is not None
    again = service.archive(ALICE, channel.id, channel.revision).channel
    assert again.revision == archived.revision
    assert code(service.archive, ALICE, channel.id, archived.revision) is ErrorCode.CONFLICT
    assert code(service.join, BOB, channel.id) is ErrorCode.CONFLICT
    failure = code(service.update, ALICE, channel.id, "x", "", archived.revision)
    assert failure is ErrorCode.CONFLICT
    page = service.list_department(BOB, DEPT, None, 20)
    assert channel.id not in [item.channel.id for item in page.items]


def test_failed_unit_rolls_back_every_write():
    service, store = make()
    store.fail_after_write = True
    with pytest.raises(RuntimeError):
        service.create(ALICE, DEPT, None, "스터디", "", KEY)
    assert not store.channels and not store.members and not store.claims


# ---- own membership -----------------------------------------------------------------------


def test_join_leave_are_idempotent_and_own_only():
    service, store = make()
    channel = new_channel(service).channel
    joined = service.join(BOB, channel.id)
    assert joined.changed and joined.channel.my_role is MemberRole.MEMBER
    assert joined.channel.channel.member_count == 2
    assert not service.join(BOB, channel.id).changed
    left = service.leave(BOB, channel.id)
    assert left.changed and left.channel_id == channel.id
    assert store.count(channel.id) == 1
    assert not service.leave(BOB, channel.id).changed
    assert (channel.id, ALICE.user_id) in store.members


def test_owner_cannot_leave_and_outsider_cannot_join_or_probe():
    service, _ = make()
    channel = new_channel(service).channel
    assert code(service.leave, ALICE, channel.id) is ErrorCode.CONFLICT
    assert code(service.join, DAVE, channel.id) is ErrorCode.FORBIDDEN
    assert code(service.leave, DAVE, channel.id) is ErrorCode.FORBIDDEN
    assert code(service.join, BOB, random_id()) is ErrorCode.NOT_FOUND


def test_revoked_member_loses_access_but_can_leave():
    service, store = make()
    channel = new_channel(service).channel
    service.join(BOB, channel.id)
    store.memberships[BOB.user_id] = (Membership(OTHER_DEPT, 2),)
    assert code(service.get, BOB, channel.id) is ErrorCode.FORBIDDEN
    assert code(service.join, BOB, channel.id) is ErrorCode.FORBIDDEN
    assert service.my_channels(BOB, None, 20).items == []
    assert service.leave(BOB, channel.id).changed


def test_cleanup_receipt_is_not_returned_when_commit_fails_and_membership_rolls_back():
    service, store = make()
    channel = new_channel(service).channel
    service.join(BOB, channel.id)
    store.memberships[BOB.user_id] = (Membership(OTHER_DEPT, 2),)
    store.fail_after_write = True
    with pytest.raises(RuntimeError):
        service.leave(BOB, channel.id)
    assert (channel.id, BOB.user_id) in store.members


def test_member_limit_enforced_under_channel_lock():
    service, store = make()
    channel = new_channel(service).channel
    from app.features.channels.domain import ChannelMembership

    for _ in range(MEMBER_LIMIT - 1):
        filler = random_id()
        store.members[(channel.id, filler)] = ChannelMembership(
            channel.id, filler, MemberRole.MEMBER, channel.created_at
        )
    assert code(service.join, BOB, channel.id) is ErrorCode.CONFLICT


def test_concurrent_joins_never_exceed_limit_on_serialized_fake():
    service, store = make()
    channel = new_channel(service).channel
    from app.features.channels.domain import ChannelMembership

    for _ in range(MEMBER_LIMIT - 2):
        filler = random_id()
        store.members[(channel.id, filler)] = ChannelMembership(
            channel.id, filler, MemberRole.MEMBER, channel.created_at
        )
    actors = [ChannelsActor(random_id()) for _ in range(6)]
    for actor in actors:
        store.memberships[actor.user_id] = (Membership(DEPT, 1),)
    outcomes: list[object] = []

    def run(actor):
        try:
            outcomes.append(service.join(actor, channel.id).changed)
        except ApiError as error:
            outcomes.append(error.code)

    threads = [threading.Thread(target=run, args=(actor,)) for actor in actors]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert outcomes.count(True) == 1
    assert store.count(channel.id) == MEMBER_LIMIT


def test_locks_are_taken_before_decision_reads():
    service, store = make()
    channel = new_channel(service).channel
    store.ops.clear()
    service.update(ALICE, channel.id, "새 이름", "", channel.revision)
    names = [op[0] for op in store.ops]
    assert names.index("lock_scope") < names.index("lock_channel") < names.index("memberships")
    assert names.index("lock_channel") < names.index("name_check")
    store.ops.clear()
    service.join(BOB, channel.id)
    names = [op[0] for op in store.ops]
    assert names.index("lock_channel") < names.index("memberships")
    store.ops.clear()
    service.create(ALICE, DEPT, None, "다른 채널", "", KEY2)
    names = [op[0] for op in store.ops]
    assert names.index("lock_scope") < names.index("memberships") < names.index("name_check")


# ---- listing / pagination -----------------------------------------------------------------


def test_department_list_is_bounded_cursor_paginated_and_scope_filtered():
    service, _ = make()
    ids = [new_channel(service, ALICE, name=f"전체{i}").channel.id for i in range(3)]
    ids += [new_channel(service, BOB, name=f"전체B{i}").channel.id for i in range(2)]
    grade3 = new_channel(service, CAROL, name="3학년", grade=3).channel.id
    seen = []
    before = None
    while True:
        page = service.list_department(ALICE, DEPT, before, 2)
        assert len(page.items) <= 2
        seen += [item.channel.id for item in page.items]
        if page.next_before is None:
            break
        before = page.next_before
    assert sorted(seen) == sorted(ids) and grade3 not in seen
    assert code(service.list_department, DAVE, DEPT, None, 20) is ErrorCode.FORBIDDEN
    assert code(service.list_department, ALICE, DEPT, None, 51) is ErrorCode.VALIDATION
    assert code(service.list_department, ALICE, DEPT, 0, 20) is ErrorCode.VALIDATION


def test_my_channels_only_lists_own_memberships():
    service, _ = make()
    mine = new_channel(service, ALICE, name="내 채널").channel
    other = new_channel(service, BOB, name="남의 채널").channel
    listed = [item.channel.id for item in service.my_channels(ALICE, None, 20).items]
    assert listed == [mine.id] and other.id not in listed


# ---- official channel request (FR-DEPT-004 submission only) -------------------------------


def test_owner_submits_official_request_pending_with_blocked_review():
    service, store = make()
    channel = new_channel(service).channel
    created = service.request_official(ALICE, channel.id, REASON, KEY)
    assert not created.replayed and created.value.status is RequestStatus.PENDING
    replay = service.request_official(ALICE, channel.id, REASON, KEY)
    assert replay.replayed and replay.value.id == created.value.id
    different = code(service.request_official, ALICE, channel.id, REASON + "!", KEY)
    assert different is ErrorCode.CONFLICT
    assert code(service.request_official, ALICE, channel.id, REASON, KEY2) is ErrorCode.CONFLICT
    assert len(store.requests) == 1
    # Requesting never makes the channel official or changes its revision.
    assert service.get(ALICE, channel.id).channel.revision == channel.revision


def test_request_reason_validated_and_archived_channel_rejected():
    service, _ = make()
    channel = new_channel(service).channel
    assert code(service.request_official, ALICE, channel.id, "짧음", KEY) is ErrorCode.VALIDATION
    service.archive(ALICE, channel.id, channel.revision)
    assert code(service.request_official, ALICE, channel.id, REASON, KEY) is ErrorCode.CONFLICT


def test_archive_cancels_pending_request_and_status_is_own_only():
    service, _ = make()
    channel = new_channel(service).channel
    request = service.request_official(ALICE, channel.id, REASON, KEY).value
    service.archive(ALICE, channel.id, channel.revision)
    assert service.get_request(ALICE, request.id).status is RequestStatus.CANCELLED
    assert code(service.get_request, BOB, request.id) is ErrorCode.NOT_FOUND
    assert code(service.get_request, ALICE, random_id()) is ErrorCode.NOT_FOUND
    assert service.my_requests(BOB, None, 20).items == []
    assert [r.id for r in service.my_requests(ALICE, None, 20).items] == [request.id]
