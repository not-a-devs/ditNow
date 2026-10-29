"""Pure RBAC-DEPT / RBAC-NOT rules (TC-V1-DEPT-001/002, TC-V1-NOT-001/002)."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from test_campus_support import DEPT_A, DEPT_B, World, assistant, student

from app.features.campus import policy
from app.features.campus.domain import (
    Audience,
    AudienceType,
    CampusActor,
    DeliveryTarget,
    Membership,
    Notice,
    NoticeStatus,
)


def make_notice(audience: Audience, status: NoticeStatus) -> Notice:
    now = datetime(2026, 10, 30, tzinfo=UTC)
    return Notice(uuid4(), audience, "t", "b", status, 1, uuid4(), now, now)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"type": AudienceType.SCHOOL, "department_id": DEPT_A},
        {"type": AudienceType.DEPARTMENT},
        {"type": AudienceType.DEPARTMENT, "department_id": DEPT_A, "grade": 1},
        {"type": AudienceType.DEPARTMENT_GRADE, "department_id": DEPT_A},
        {"type": AudienceType.DEPARTMENT_GRADE, "department_id": DEPT_A, "grade": 0},
        {"type": AudienceType.DEPARTMENT_GRADE, "department_id": DEPT_A, "grade": 7},
    ],
)
def test_audience_shape_rejected(kwargs):
    with pytest.raises(ValueError):
        Audience(**kwargs)


def test_channel_access_is_department_and_grade_isolated():
    world = World()
    a2 = student(DEPT_A, 2)
    assert policy.can_access_channel(a2, world.a_all)
    assert policy.can_access_channel(a2, world.a_2)
    assert not policy.can_access_channel(a2, world.a_1)
    assert not policy.can_access_channel(a2, world.b_all)
    assert not policy.can_access_channel(a2, world.b_2)  # same grade number, other department


def test_department_only_membership_cannot_enter_grade_channel():
    world = World()
    staff = CampusActor(uuid4(), (Membership(DEPT_A, None),))
    assert policy.can_access_channel(staff, world.a_all)
    assert not policy.can_access_channel(staff, world.a_2)


def test_actor_without_membership_sees_nothing():
    world = World()
    applicant = CampusActor(uuid4())
    assert policy.visible_channels(applicant, world.channels.rows.values()) == []
    assert policy.actor_audiences(applicant) == []
    published = make_notice(Audience(AudienceType.SCHOOL), NoticeStatus.PUBLISHED)
    assert not policy.can_read_notice(applicant, published)


def test_author_scope_is_exact_match():
    grade2 = Audience(AudienceType.DEPARTMENT_GRADE, DEPT_A, 2)
    ta = assistant(DEPT_A, 2)
    assert policy.can_author(ta, grade2)
    assert not policy.can_author(ta, Audience(AudienceType.DEPARTMENT_GRADE, DEPT_A, 1))
    assert not policy.can_author(ta, Audience(AudienceType.DEPARTMENT, DEPT_A))
    assert not policy.can_author(ta, Audience(AudienceType.DEPARTMENT_GRADE, DEPT_B, 2))
    assert not policy.can_author(student(DEPT_A, 2), grade2)


def test_notice_read_rules():
    grade2 = Audience(AudienceType.DEPARTMENT_GRADE, DEPT_A, 2)
    draft = make_notice(grade2, NoticeStatus.DRAFT)
    published = make_notice(grade2, NoticeStatus.PUBLISHED)
    a2, a1, b2 = student(DEPT_A, 2), student(DEPT_A, 1), student(DEPT_B, 2)
    assert not policy.can_read_notice(a2, draft)
    assert policy.can_read_notice(assistant(DEPT_A, 2), draft)
    assert policy.can_read_notice(a2, published)
    assert not policy.can_read_notice(a1, published)
    assert not policy.can_read_notice(b2, published)


def test_delivery_targets_follow_dflt_004():
    assert policy.delivery_targets(Audience(AudienceType.SCHOOL)) == []
    assert policy.delivery_targets(Audience(AudienceType.DEPARTMENT, DEPT_A)) == [
        DeliveryTarget(DEPT_A, None)
    ]
    assert policy.delivery_targets(Audience(AudienceType.DEPARTMENT_GRADE, DEPT_A, 2)) == [
        DeliveryTarget(DEPT_A, 2)
    ]


def test_actor_audiences_cover_own_scopes_only():
    audiences = set(policy.actor_audiences(student(DEPT_A, 2)))
    assert audiences == {
        Audience(AudienceType.SCHOOL),
        Audience(AudienceType.DEPARTMENT, DEPT_A),
        Audience(AudienceType.DEPARTMENT_GRADE, DEPT_A, 2),
    }
